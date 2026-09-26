from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
)


def require_decimal_string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Money must be provided as a decimal string")
    return value


OpeningBalance = Annotated[
    Decimal,
    BeforeValidator(require_decimal_string, json_schema_input_type=str),
    Field(
        ge=0,
        le=Decimal("9999999999999999.99"),
        max_digits=18,
        decimal_places=2,
        allow_inf_nan=False,
    ),
]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    opening_balance: OpeningBalance = Decimal("0.00")


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_name: str
    balance: Decimal
    created_at: datetime

    @field_serializer("balance", when_used="json")
    def serialize_balance(self, value: Decimal) -> str:
        return format(value, ".2f")
