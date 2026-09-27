from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update

from app.transfers.models import Transfer
from tests.helpers import payload

pytestmark = pytest.mark.integration


def test_history_includes_both_directions_and_excludes_other_accounts(
    transfer_client: TestClient, account_factory: Callable
) -> None:
    alice, bob, charlie, other = account_factory("100", "100", "100", "0")
    responses = [
        transfer_client.post(
            "/transfers",
            json=payload(source, destination, "0.10"),
            headers={"Idempotency-Key": str(uuid4())},
        )
        for source, destination in [(alice, bob), (charlie, alice), (bob, other)]
    ]
    assert all(response.status_code == 201 for response in responses)
    response = transfer_client.get(f"/accounts/{alice}/transactions")
    assert response.status_code == 200
    page = response.json()
    assert page == {
        "items": [
            {**responses[1].json(), "direction": "credit"},
            {**responses[0].json(), "direction": "debit"},
        ],
        "limit": 20,
        "offset": 0,
        "has_more": False,
    }
    assert "idempotency_key" not in page["items"][0]


def test_history_empty_and_offset_beyond_end(
    transfer_client: TestClient, account_factory: Callable
) -> None:
    account = account_factory("100")[0]
    for offset in (0, 50):
        response = transfer_client.get(
            f"/accounts/{account}/transactions", params={"offset": offset}
        )
        assert response.status_code == 200
        assert response.json() == {
            "items": [],
            "limit": 20,
            "offset": offset,
            "has_more": False,
        }


def test_history_pagination_and_deterministic_timestamp_ties(
    transfer_client: TestClient, account_factory: Callable, test_engine: Engine
) -> None:
    source, destination = account_factory("100", "0")
    transfers = []
    for _ in range(5):
        response = transfer_client.post(
            "/transfers",
            json=payload(source, destination, "1"),
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201
        transfers.append(response.json())

    # Control time explicitly: creation time determines order, then UUID breaks ties.
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with test_engine.begin() as connection:
        connection.execute(
            update(Transfer)
            .where(Transfer.source_account_id == source)
            .values(created_at=timestamp)
        )
        connection.execute(
            update(Transfer)
            .where(Transfer.id == UUID(transfers[0]["id"]))
            .values(created_at=timestamp + timedelta(seconds=1))
        )
    expected = [transfers[0]["id"]] + sorted(
        [item["id"] for item in transfers[1:]], reverse=True
    )
    collected = []
    for offset, size, more in [
        (0, 2, True),
        (2, 2, True),
        (4, 1, False),
        (6, 0, False),
    ]:
        response = transfer_client.get(
            f"/accounts/{source}/transactions", params={"limit": 2, "offset": offset}
        )
        assert response.status_code == 200
        page = response.json()
        assert page["limit"] == 2 and page["offset"] == offset
        assert page["has_more"] is more
        assert len(page["items"]) == size
        collected.extend(item["id"] for item in page["items"])
    assert collected == expected
    exact = transfer_client.get(
        f"/accounts/{source}/transactions", params={"limit": 5}
    ).json()
    assert len(exact["items"]) == 5 and exact["has_more"] is False
    assert (
        transfer_client.get(
            f"/accounts/{source}/transactions", params={"limit": 100}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": 101},
        {"limit": "bad"},
        {"offset": -1},
        {"offset": "bad"},
        {"limit": "1.5"},
    ],
)
def test_history_rejects_invalid_pagination(
    transfer_client: TestClient, account_factory: Callable, params: dict
) -> None:
    account = account_factory("0")[0]
    response = transfer_client.get(f"/accounts/{account}/transactions", params=params)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_history_missing_and_invalid_account(transfer_client: TestClient) -> None:
    response = transfer_client.get(f"/accounts/{uuid4()}/transactions")
    assert response.status_code == 404
    assert response.json() == {"detail": "Account not found"}
    assert transfer_client.get("/accounts/invalid/transactions").status_code == 422


def test_history_excludes_failures_and_does_not_duplicate_replays(
    transfer_client: TestClient, account_factory: Callable
) -> None:
    source, destination = account_factory("10", "0")
    key = str(uuid4())
    first = transfer_client.post(
        "/transfers",
        json=payload(source, destination),
        headers={"Idempotency-Key": key},
    )
    replay = transfer_client.post(
        "/transfers",
        json=payload(source, destination),
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == replay.status_code == 201
    failed = transfer_client.post(
        "/transfers",
        json=payload(source, destination),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert failed.status_code == 409
    page = transfer_client.get(f"/accounts/{source}/transactions").json()
    assert page["items"] == [{**first.json(), "direction": "debit"}]
    assert page["has_more"] is False
