from uuid import UUID

from sqlalchemy.orm import Session

from app.accounts import repository
from app.accounts.models import Account
from app.accounts.schemas import AccountCreate


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
