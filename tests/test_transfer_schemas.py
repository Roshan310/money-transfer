from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.transfers.schemas import TransferCreate


@pytest.mark.parametrize("amount", ["0.01", "10", "10.00", "9999999999999999.99"])
def test_valid_transfer_amounts(amount: str) -> None:
    transfer = TransferCreate(
        source_account_id=uuid4(), destination_account_id=uuid4(), amount=amount
    )
    assert transfer.amount == Decimal(amount)


@pytest.mark.parametrize(
    "amount",
    ["0", "-1", "1.001", "10000000000000000", "NaN", "Infinity", "abc", 1, 0.1, True],
)
def test_invalid_transfer_amounts(amount: object) -> None:
    with pytest.raises(ValidationError):
        TransferCreate.model_validate(
            {
                "source_account_id": uuid4(),
                "destination_account_id": uuid4(),
                "amount": amount,
            }
        )


def test_same_account_transfer_is_invalid() -> None:
    account_id = uuid4()
    with pytest.raises(ValidationError, match="must be different"):
        TransferCreate(
            source_account_id=account_id, destination_account_id=account_id, amount="1"
        )
