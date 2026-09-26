from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.transfers.models import Transfer


def get_by_idempotency_key(session: Session, key: str) -> Transfer | None:
    return session.scalar(select(Transfer).where(Transfer.idempotency_key == key))


def get_account_history(
    session: Session, account_id: UUID, *, limit: int, offset: int
) -> list[Transfer]:
    statement = (
        select(Transfer)
        .where(
            or_(
                Transfer.source_account_id == account_id,
                Transfer.destination_account_id == account_id,
            )
        )
        .order_by(Transfer.created_at.desc(), Transfer.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


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
