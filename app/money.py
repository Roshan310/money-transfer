from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field

MAX_BALANCE = Decimal("9999999999999999.99")


def require_decimal_string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Money must be provided as a decimal string")
    return value


Money = Annotated[
    Decimal,
    BeforeValidator(require_decimal_string, json_schema_input_type=str),
    Field(
        le=MAX_BALANCE,
        max_digits=18,
        decimal_places=2,
        allow_inf_nan=False,
    ),
]
NonnegativeMoney = Annotated[Money, Field(ge=0)]
PositiveMoney = Annotated[Money, Field(gt=0)]


def format_money(value: Decimal) -> str:
    return format(value, ".2f")
