from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.accounts.schemas import AccountCreate


def test_default_balance_and_trimmed_name() -> None:
    account = AccountCreate(owner_name="  Alice  ")
    assert account.owner_name == "Alice"
    assert account.opening_balance == Decimal("0.00")


@pytest.mark.parametrize("amount", ["0", "0.01", "100.50", "9999999999999999.99"])
def test_valid_balances(amount: str) -> None:
    assert AccountCreate(
        owner_name="Alice", opening_balance=amount
    ).opening_balance == (Decimal(amount))


@pytest.mark.parametrize(
    "amount",
    ["-0.01", "1.001", "10000000000000000", "NaN", "Infinity", "abc", 1.5, 1, True],
)
def test_invalid_balances(amount: object) -> None:
    with pytest.raises(ValidationError):
        AccountCreate.model_validate({"owner_name": "Alice", "opening_balance": amount})


@pytest.mark.parametrize("name", ["", "   ", "a" * 101, None, 123])
def test_invalid_names(name: object) -> None:
    with pytest.raises(ValidationError):
        AccountCreate.model_validate({"owner_name": name})
