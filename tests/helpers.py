from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.transfers.models import Transfer


def payload(source: UUID, destination: UUID, amount: str = "10.00") -> dict:
    return {
        "source_account_id": str(source),
        "destination_account_id": str(destination),
        "amount": amount,
    }


def balances(engine: Engine, account_ids: list[UUID]) -> list[Decimal]:
    with Session(engine) as session:
        return [session.get(Account, account_id).balance for account_id in account_ids]


def transfer_count(engine: Engine, source: UUID) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count())
            .select_from(Transfer)
            .where(Transfer.source_account_id == source)
        )
