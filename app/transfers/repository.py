from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.transfers.models import Transfer


def get_by_idempotency_key(session: Session, key: str) -> Transfer | None:
    return session.scalar(select(Transfer).where(Transfer.idempotency_key == key))


def insert_transfer(
    session: Session,
    *,
    source_account_id: UUID,
    destination_account_id: UUID,
    amount: Decimal,
    key: str,
) -> Transfer | None:
    statement = (
        insert(Transfer)
        .values(
            source_account_id=source_account_id,
            destination_account_id=destination_account_id,
            amount=amount,
            idempotency_key=key,
        )
        .on_conflict_do_nothing(constraint="uq_transfers_idempotency_key")
        .returning(Transfer)
    )
    return session.scalar(statement)
