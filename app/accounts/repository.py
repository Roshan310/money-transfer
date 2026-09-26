from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.accounts.models import Account


def insert_account(session: Session, owner_name: str, balance: Decimal) -> Account:
    account = Account(owner_name=owner_name, balance=balance)
    session.add(account)
    session.flush()
    return account


def get_account(session: Session, account_id: UUID) -> Account | None:
    return session.get(Account, account_id)
