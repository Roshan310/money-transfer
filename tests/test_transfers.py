from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.money import MAX_BALANCE
from app.transfers.models import Transfer
from tests.helpers import balances, payload, transfer_count

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("amount", ["0.10", "100.00"])
def test_transfer_commits_and_persists(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
    amount: str,
) -> None:
    source, destination = account_factory("100.00", "0.00")
    response = transfer_client.post(
        "/api/v1/transfers",
        json=payload(source, destination, amount),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    result = response.json()
    assert set(result) == {
        "id",
        "source_account_id",
        "destination_account_id",
        "amount",
        "created_at",
    }
    assert result["source_account_id"] == str(source)
    assert result["destination_account_id"] == str(destination)
    assert result["amount"] == amount
    assert datetime.fromisoformat(result["created_at"]).tzinfo is not None
    with Session(test_engine) as reader:
        transfer = reader.get(Transfer, UUID(result["id"]))
        assert transfer is not None
        assert transfer.amount == Decimal(amount)
    assert balances(test_engine, [source, destination]) == [
        Decimal("100.00") - Decimal(amount),
        Decimal(amount),
    ]
    assert transfer_client.get(f"/api/v1/accounts/{source}").json()[
        "balance"
    ] == format(Decimal("100.00") - Decimal(amount), ".2f")


@pytest.mark.parametrize("key", [None, "", "   ", "x" * 129])
def test_idempotency_header_required_and_validated(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
    key: str | None,
) -> None:
    source, destination = account_factory("100", "0")
    response = transfer_client.post(
        "/api/v1/transfers",
        json=payload(source, destination),
        headers={} if key is None else {"Idempotency-Key": key},
    )
    assert response.status_code == 422
    assert balances(test_engine, [source, destination]) == [
        Decimal("100"),
        Decimal("0"),
    ]
    assert transfer_count(test_engine, source) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "1.001"},
        {"amount": "10000000000000000"},
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"amount": 0.1},
        {"source_account_id": "invalid"},
        {"unexpected": "field"},
    ],
)
def test_invalid_transfer_request(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
    changes: dict,
) -> None:
    source, destination = account_factory("100", "0")
    response = transfer_client.post(
        "/api/v1/transfers",
        json=payload(source, destination) | changes,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    assert "detail" in response.json()
    assert balances(test_engine, [source, destination]) == [
        Decimal("100"),
        Decimal("0"),
    ]
    assert transfer_count(test_engine, source) == 0


def test_self_transfer_is_rejected(transfer_client: TestClient) -> None:
    account_id = uuid4()
    response = transfer_client.post(
        "/api/v1/transfers",
        json=payload(account_id, account_id),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("missing_source", [True, False])
def test_missing_account(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
    missing_source: bool,
) -> None:
    existing = account_factory("100")[0]
    source, destination = (uuid4(), existing) if missing_source else (existing, uuid4())
    response = transfer_client.post(
        "/api/v1/transfers",
        json=payload(source, destination),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 404
    assert response.json() == {
        "detail": "Source account not found"
        if missing_source
        else "Destination account not found"
    }
    assert balances(test_engine, [existing]) == [Decimal("100")]


@pytest.mark.parametrize(
    "source_balance,destination_balance,amount,message",
    [
        ("5", "0", "10", "Insufficient funds"),
        ("10", str(MAX_BALANCE), "0.01", "Destination balance would exceed the limit"),
    ],
)
def test_business_failure_is_atomic(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
    source_balance: str,
    destination_balance: str,
    amount: str,
    message: str,
) -> None:
    ids = account_factory(source_balance, destination_balance)
    response = transfer_client.post(
        "/api/v1/transfers",
        json=payload(*ids, amount),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": message}
    assert balances(test_engine, ids) == [
        Decimal(source_balance),
        Decimal(destination_balance),
    ]
    assert transfer_count(test_engine, ids[0]) == 0


def test_failure_after_balance_flush_rolls_everything_back(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
) -> None:
    ids = account_factory("100", "0")
    key = str(uuid4())

    def fail_after_flush(session, flush_context):
        raise RuntimeError("Injected failure after database writes")

    event.listen(Session, "after_flush_postexec", fail_after_flush)
    try:
        response = transfer_client.post(
            "/api/v1/transfers", json=payload(*ids), headers={"Idempotency-Key": key}
        )
    finally:
        event.remove(Session, "after_flush_postexec", fail_after_flush)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert balances(test_engine, ids) == [Decimal("100"), Decimal("0")]
    assert transfer_count(test_engine, ids[0]) == 0
    assert (
        transfer_client.get(f"/api/v1/accounts/{ids[0]}/transactions").json()["items"]
        == []
    )
    retried = transfer_client.post(
        "/api/v1/transfers", json=payload(*ids), headers={"Idempotency-Key": key}
    )
    assert retried.status_code == 201
    assert balances(test_engine, ids) == [Decimal("90"), Decimal("10")]


def test_replay_returns_original_result_after_balances_change(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
) -> None:
    source, destination = account_factory("10", "0")
    key = str(uuid4())
    first = transfer_client.post(
        "/api/v1/transfers",
        json=payload(source, destination, "10"),
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 201
    reverse = transfer_client.post(
        "/api/v1/transfers",
        json=payload(destination, source, "10"),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert reverse.status_code == 201
    second = transfer_client.post(
        "/api/v1/transfers",
        json=payload(source, destination, "10.00"),
        headers={"Idempotency-Key": key},
    )
    assert second.status_code == 201
    assert second.json() == first.json()
    assert balances(test_engine, [source, destination]) == [Decimal("10"), Decimal("0")]
    assert transfer_count(test_engine, source) == 1


def test_replay_when_source_is_now_empty(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
) -> None:
    ids = account_factory("10", "0")
    key = str(uuid4())
    responses = [
        transfer_client.post(
            "/api/v1/transfers", json=payload(*ids), headers={"Idempotency-Key": key}
        )
        for _ in range(2)
    ]
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    assert balances(test_engine, ids) == [Decimal("0"), Decimal("10")]
    assert transfer_count(test_engine, ids[0]) == 1


@pytest.mark.parametrize(
    "changed_field", ["amount", "source_account_id", "destination_account_id"]
)
def test_key_reuse_with_changed_payload_conflicts(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
    changed_field: str,
) -> None:
    source, destination, other = account_factory("100", "0", "100")
    key = str(uuid4())
    original = payload(source, destination)
    assert (
        transfer_client.post(
            "/api/v1/transfers", json=original, headers={"Idempotency-Key": key}
        ).status_code
        == 201
    )
    changed = original | {
        changed_field: "11" if changed_field == "amount" else str(other)
    }
    response = transfer_client.post(
        "/api/v1/transfers", json=changed, headers={"Idempotency-Key": key}
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Idempotency key was used for a different transfer"
    }
    assert balances(test_engine, [source, destination, other]) == [
        Decimal("90"),
        Decimal("10"),
        Decimal("100"),
    ]


def test_failed_key_can_be_retried_after_funding(
    transfer_client: TestClient,
    account_factory: Callable,
    test_engine: Engine,
) -> None:
    source, destination, donor = account_factory("0", "0", "10")
    key = str(uuid4())
    first = transfer_client.post(
        "/api/v1/transfers",
        json=payload(source, destination),
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 409
    funding = transfer_client.post(
        "/api/v1/transfers",
        json=payload(donor, source),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert funding.status_code == 201
    retry = transfer_client.post(
        "/api/v1/transfers",
        json=payload(source, destination),
        headers={"Idempotency-Key": key},
    )
    assert retry.status_code == 201
    assert balances(test_engine, [source, destination, donor]) == [
        Decimal("0"),
        Decimal("10"),
        Decimal("0"),
    ]


@pytest.mark.parametrize(
    "amount,same_account,missing_destination,constraint",
    [
        ("0", False, False, "ck_transfers_amount_range"),
        ("-1", False, False, "ck_transfers_amount_range"),
        ("NaN", False, False, "ck_transfers_amount_range"),
        ("1", True, False, "ck_transfers_distinct_accounts"),
        ("1", False, True, "fk_transfers_destination_account_id"),
    ],
)
def test_database_constraints(
    account_factory: Callable,
    test_engine: Engine,
    amount: str,
    same_account: bool,
    missing_destination: bool,
    constraint: str,
) -> None:
    source, destination = account_factory("100", "0")
    if same_account:
        destination = source
    elif missing_destination:
        destination = uuid4()
    with Session(test_engine) as session:
        session.add(
            Transfer(
                source_account_id=source,
                destination_account_id=destination,
                amount=Decimal(amount),
                idempotency_key=str(uuid4()),
            )
        )
        with pytest.raises(IntegrityError) as error:
            session.commit()
        assert error.value.orig.diag.constraint_name == constraint
