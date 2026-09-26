from sqlalchemy.orm import Session

from app.accounts import repository as accounts_repository
from app.money import MAX_BALANCE
from app.transfers import repository
from app.transfers.errors import TransferAccountNotFoundError, TransferConflictError
from app.transfers.models import Transfer
from app.transfers.schemas import TransferCreate


def validate_replay(transfer: Transfer, data: TransferCreate) -> Transfer:
    if (
        transfer.source_account_id != data.source_account_id
        or transfer.destination_account_id != data.destination_account_id
        or transfer.amount != data.amount
    ):
        raise TransferConflictError("Idempotency key was used for a different transfer")
    return transfer


def create_transfer(session: Session, data: TransferCreate, key: str) -> Transfer:
    with session.begin():
        existing = repository.get_by_idempotency_key(session, key)
        if existing is not None:
            return validate_replay(existing, data)

        accounts = accounts_repository.lock_accounts(
            session, (data.source_account_id, data.destination_account_id)
        )
        if data.source_account_id not in accounts:
            raise TransferAccountNotFoundError("Source account not found")
        if data.destination_account_id not in accounts:
            raise TransferAccountNotFoundError("Destination account not found")

        # Reserve the key only after taking account locks. This prevents implicit
        # foreign-key locks from being acquired before our ordered row locks.
        transfer = repository.insert_transfer(
            session,
            source_account_id=data.source_account_id,
            destination_account_id=data.destination_account_id,
            amount=data.amount,
            key=key,
        )
        if transfer is None:
            # READ COMMITTED gives this separate SELECT a new snapshot, including
            # the competing transaction whose commit prevented our INSERT.
            existing = repository.get_by_idempotency_key(session, key)
            if existing is None:
                raise RuntimeError("Conflicting transfer disappeared")
            return validate_replay(existing, data)

        source = accounts[data.source_account_id]
        destination = accounts[data.destination_account_id]
        if source.balance < data.amount:
            raise TransferConflictError("Insufficient funds")
        if destination.balance + data.amount > MAX_BALANCE:
            raise TransferConflictError("Destination balance would exceed the limit")

        source.balance -= data.amount
        destination.balance += data.amount
        session.flush()
    return transfer
