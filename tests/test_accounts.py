from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts import service
from app.accounts.models import Account
from app.accounts.schemas import AccountCreate
from app.database import get_session
from app.main import create_app

pytestmark = pytest.mark.integration


def test_creation_commits_before_response(test_engine: Engine) -> None:
    app = create_app()

    def fresh_session() -> Iterator[Session]:
        with Session(test_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = fresh_session
    account_id = None
    try:
        with TestClient(app) as client:
            response = client.post(
                "/accounts",
                json={"owner_name": "Commit test", "opening_balance": "0.10"},
            )
            assert response.status_code == 201
            account_id = UUID(response.json()["id"])
            # A separate connection must see the account after the response.
            with Session(test_engine) as reader:
                account = reader.get(Account, account_id)
                assert account is not None
                assert account.balance == Decimal("0.10")
            assert client.get(f"/accounts/{account_id}").status_code == 200
    finally:
        if account_id is not None:
            with test_engine.begin() as connection:
                connection.execute(delete(Account).where(Account.id == account_id))


@pytest.mark.parametrize("balance", ["100.10", "9999999999999999.99"])
def test_create_and_get_account(
    client: TestClient, session: Session, balance: str
) -> None:
    response = client.post(
        "/accounts", json={"owner_name": "  Alice  ", "opening_balance": balance}
    )
    assert response.status_code == 201
    account = response.json()
    account_id = UUID(account["id"])
    assert account["owner_name"] == "Alice"
    assert account["balance"] == balance
    assert datetime.fromisoformat(account["created_at"]).tzinfo is not None

    stored = session.get(Account, account_id)
    assert stored is not None
    assert stored.balance == Decimal(balance)

    fetched = client.get(f"/accounts/{account_id}")
    assert fetched.status_code == 200
    assert fetched.json() == account


def test_default_balance_and_distinct_ids(client: TestClient) -> None:
    first = client.post("/accounts", json={"owner_name": "Alice"})
    second = client.post("/accounts", json={"owner_name": "Alice"})
    assert first.status_code == second.status_code == 201
    assert first.json()["balance"] == second.json()["balance"] == "0.00"
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"owner_name": " "},
        {"owner_name": "a" * 101},
        {"owner_name": "Alice", "opening_balance": "-1"},
        {"owner_name": "Alice", "opening_balance": "1.001"},
        {"owner_name": "Alice", "opening_balance": "10000000000000000"},
        {"owner_name": "Alice", "opening_balance": "NaN"},
        {"owner_name": "Alice", "opening_balance": 1.25},
        {"owner_name": "Alice", "balance": "100.00"},
    ],
)
def test_invalid_create_request(client: TestClient, payload: dict) -> None:
    response = client.post("/accounts", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_missing_account(client: TestClient) -> None:
    response = client.get(f"/accounts/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Account not found"}


def test_invalid_account_id(client: TestClient) -> None:
    assert client.get("/accounts/not-a-uuid").status_code == 422


def test_database_rejects_negative_balance(session: Session) -> None:
    session.add(Account(owner_name="Alice", balance=Decimal("-0.01")))
    with pytest.raises(IntegrityError) as error:
        session.flush()
    assert error.value.orig.diag.constraint_name == "ck_accounts_balance_nonnegative"
    session.rollback()


def test_database_rejects_nan_balance(session: Session) -> None:
    session.add(Account(owner_name="Alice", balance=Decimal("NaN")))
    with pytest.raises(IntegrityError) as error:
        session.flush()
    assert error.value.orig.diag.constraint_name == "ck_accounts_balance_upper_bound"
    session.rollback()


def test_failed_creation_rolls_back_and_session_remains_usable(
    session: Session,
) -> None:
    # Bypass API validation to exercise the service's rollback on a DB failure.
    invalid = AccountCreate.model_construct(
        owner_name="Alice", opening_balance=Decimal("-0.01")
    )
    with pytest.raises(IntegrityError):
        service.create_account(session, invalid)
    account = service.create_account(session, AccountCreate(owner_name="Bob"))
    assert account.balance == Decimal("0.00")
