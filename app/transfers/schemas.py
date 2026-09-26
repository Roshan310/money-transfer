from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer, model_validator

from app.money import PositiveMoney, format_money


class TransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_account_id: UUID
    destination_account_id: UUID
    amount: PositiveMoney

    @model_validator(mode="after")
    def validate_distinct_accounts(self) -> Self:
        if self.source_account_id == self.destination_account_id:
            raise ValueError("Source and destination accounts must be different")
        return self


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal
    created_at: datetime

    @field_serializer("amount", when_used="json")
    def serialize_amount(self, value: Decimal) -> str:
        return format_money(value)
