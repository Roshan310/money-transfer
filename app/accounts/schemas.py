from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_serializer,
)

from app.money import NonnegativeMoney, format_money
from app.transfers.schemas import TransferRead


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    opening_balance: NonnegativeMoney = Decimal("0.00")


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_name: str
    balance: Decimal
    created_at: datetime

    @field_serializer("balance", when_used="json")
    def serialize_balance(self, value: Decimal) -> str:
        return format_money(value)


class AccountTransactionRead(TransferRead):
    direction: Literal["debit", "credit"]


class AccountTransactionPage(BaseModel):
    items: list[AccountTransactionRead]
    limit: int
    offset: int
    has_more: bool
