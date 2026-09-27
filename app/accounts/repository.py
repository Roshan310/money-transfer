from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account


def insert_account(session: Session, owner_name: str, balance: Decimal) -> Account:
    account = Account(owner_name=owner_name, balance=balance)
    session.add(account)
    session.flush()
    return account


def get_account(session: Session, account_id: UUID) -> Account | None:
    return session.get(Account, account_id)


# I implemented this only for the ease of finding account uuids for transfer tests.

def get_all_accounts(session: Session) -> list[Account]:
    return session.scalars(select(Account)).all()

def lock_accounts(
    session: Session, account_ids: tuple[UUID, UUID]
) -> dict[UUID, Account]:
    accounts = {}

    # Every transfer acquires locks in the same order, including reverse transfers.
    # A is sending money to B, and B is sending money to A. If we don't acquire locks in the same order,
    # we can have a deadlock.
    # This is a simple way to avoid deadlocks: always acquire locks in the same order.

    for account_id in sorted(account_ids):
        account = session.scalar(
            select(Account)
            .where(Account.id == account_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if account is not None:
            accounts[account_id] = account
    return accounts
