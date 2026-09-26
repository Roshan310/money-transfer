from uuid import UUID

from sqlalchemy.orm import Session

from app.accounts import repository
from app.accounts.models import Account
from app.accounts.schemas import (
    AccountCreate,
    AccountTransactionPage,
    AccountTransactionRead,
)
from app.transfers import repository as transfers_repository


class AccountNotFoundError(Exception):
    pass


def create_account(session: Session, data: AccountCreate) -> Account:
    with session.begin():
        account = repository.insert_account(
            session, owner_name=data.owner_name, balance=data.opening_balance
        )
    return account


def get_account(session: Session, account_id: UUID) -> Account:
    account = repository.get_account(session, account_id)
    if account is None:
        raise AccountNotFoundError
    return account


def get_all_accounts(session: Session) -> list[Account]:
    return repository.get_all_accounts(session)


def get_transaction_history(
    session: Session, account_id: UUID, *, limit: int, offset: int
) -> AccountTransactionPage:
    get_account(session, account_id)
    transfers = transfers_repository.get_account_history(
        session, account_id, limit=limit + 1, offset=offset
    )
    return AccountTransactionPage(
        items=[
            AccountTransactionRead(
                id=transfer.id,
                source_account_id=transfer.source_account_id,
                destination_account_id=transfer.destination_account_id,
                amount=transfer.amount,
                created_at=transfer.created_at,
                direction=(
                    "debit" if transfer.source_account_id == account_id else "credit"
                ),
            )
            for transfer in transfers[:limit]
        ],
        limit=limit,
        offset=offset,
        has_more=len(transfers) > limit,
    )
