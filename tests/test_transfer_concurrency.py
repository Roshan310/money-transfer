from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text

from app.accounts.models import Account
from tests.helpers import balances, payload, transfer_count

pytestmark = pytest.mark.integration


def post_overlapping(
    engine: Engine,
    client: TestClient,
    account_ids: list[UUID],
    requests: list[tuple[dict, str]],
) -> list:
    barrier = Barrier(len(requests) + 1)

    def post(body: dict, key: str):
        barrier.wait(timeout=5)
        return client.post("/transfers", json=body, headers={"Idempotency-Key": key})

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        with engine.begin() as blocker:
            blocker.execute(
                select(Account.id)
                .where(Account.id.in_(account_ids))
                .order_by(Account.id)
                .with_for_update()
            ).all()
            futures = [executor.submit(post, body, key) for body, key in requests]
            barrier.wait(timeout=5)
            # Prove every request is waiting on a database lock before releasing
            # the blocker. Overlap is established by DB state, not timing guesses.
            with engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as observer:
                deadline = monotonic() + 5
                while True:
                    waiting = observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() "
                            "AND application_name = 'money-transfer-tests' "
                            "AND wait_event_type = 'Lock'"
                        )
                    )
                    if waiting >= len(requests):
                        break
                    if monotonic() >= deadline:
                        pytest.fail(
                            f"Only {waiting}/{len(requests)} requests reached row locks"
                        )
                    sleep(0.01)
        return [future.result(timeout=15) for future in futures]


def test_competing_withdrawals_never_overdraw(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
) -> None:
    ids = account_factory("100", *("0" for _ in range(8)))
    source, *destinations = ids
    results = post_overlapping(
        test_engine,
        transfer_client,
        ids,
        [
            (payload(source, destination, "30"), str(uuid4()))
            for destination in destinations
        ],
    )
    codes = [response.status_code for response in results]
    assert codes.count(201) == 3
    assert codes.count(409) == 5
    for response in results:
        if response.status_code == 409:
            assert response.json() == {"detail": "Insufficient funds"}
    final = balances(test_engine, ids)
    assert final[0] == Decimal("10")
    assert all(balance >= 0 for balance in final)
    assert sum(final) == Decimal("100")
    assert transfer_count(test_engine, source) == 3
    for destination, response in zip(destinations, results, strict=True):
        assert balances(test_engine, [destination]) == [
            Decimal("30") if response.status_code == 201 else Decimal("0")
        ]


def test_simultaneous_credits_do_not_lose_updates(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
) -> None:
    ids = account_factory("0", *("10" for _ in range(4)))
    destination, *sources = ids
    results = post_overlapping(
        test_engine,
        transfer_client,
        ids,
        [(payload(source, destination), str(uuid4())) for source in sources],
    )
    assert [response.status_code for response in results] == [201] * 4
    assert balances(test_engine, ids) == [Decimal("40"), *([Decimal("0")] * 4)]
    assert sum(transfer_count(test_engine, source) for source in sources) == 4


def test_opposite_direction_transfers_do_not_deadlock(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
) -> None:
    first, second = ids = account_factory("100", "100")
    results = post_overlapping(
        test_engine,
        transfer_client,
        ids,
        [
            (payload(first, second, "30"), str(uuid4())),
            (payload(second, first, "20"), str(uuid4())),
        ],
    )
    assert [response.status_code for response in results] == [201, 201]
    assert balances(test_engine, ids) == [Decimal("90"), Decimal("110")]
    assert (
        transfer_count(test_engine, first) == transfer_count(test_engine, second) == 1
    )


def test_simultaneous_identical_keys_transfer_once(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
) -> None:
    ids = account_factory("10", "0")
    key = str(uuid4())
    results = post_overlapping(
        test_engine,
        transfer_client,
        ids,
        [(payload(*ids), key)] * 4,
    )
    assert [response.status_code for response in results] == [201] * 4
    assert all(response.json() == results[0].json() for response in results)
    assert balances(test_engine, ids) == [Decimal("0"), Decimal("10")]
    assert transfer_count(test_engine, ids[0]) == 1


@pytest.mark.parametrize("disjoint", [False, True])
def test_simultaneous_key_reuse_with_different_payloads(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
    disjoint: bool,
) -> None:
    source, destination, other_source, other_destination = ids = account_factory(
        "100", "0", "100", "0"
    )
    key = str(uuid4())
    second_body = (
        payload(other_source, other_destination, "20")
        if disjoint
        else payload(source, destination, "20")
    )
    results = post_overlapping(
        test_engine,
        transfer_client,
        ids,
        [(payload(source, destination), key), (second_body, key)],
    )
    assert sorted(response.status_code for response in results) == [201, 409]
    winner = next(
        response.json() for response in results if response.status_code == 201
    )
    loser = next(response for response in results if response.status_code == 409)
    assert loser.json() == {
        "detail": "Idempotency key was used for a different transfer"
    }
    expected = dict(
        zip(
            ids,
            [Decimal("100"), Decimal("0"), Decimal("100"), Decimal("0")],
            strict=True,
        )
    )
    expected[UUID(winner["source_account_id"])] -= Decimal(winner["amount"])
    expected[UUID(winner["destination_account_id"])] += Decimal(winner["amount"])
    final = balances(test_engine, ids)
    assert final == [expected[account_id] for account_id in ids]
    assert sum(final) == Decimal("200")
    assert (
        transfer_count(test_engine, source) + transfer_count(test_engine, other_source)
        == 1
    )
