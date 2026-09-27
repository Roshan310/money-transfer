from collections.abc import Callable, Iterator
from decimal import Decimal
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, delete, or_
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.config import get_settings
from app.database import get_session
from app.main import create_app
from app.transfers.models import Transfer


class TestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    test_database_url: str


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    url = make_url(TestSettings().test_database_url)
    development_url = make_url(get_settings().database_url)
    if (
        url.get_backend_name() != "postgresql"
        or not url.database
        or not url.database.endswith("_test")
        or (url.host, url.port, url.database)
        == (development_url.host, development_url.port, development_url.database)
    ):
        raise ValueError("Tests require a separate PostgreSQL database ending in _test")

    engine = create_engine(
        url,
        connect_args={
            "options": (
                "-c statement_timeout=10000 -c lock_timeout=8000 "
                "-c application_name=money-transfer-tests"
            )
        },
    )
    try:
        # Alembic owns migration transactions, including concurrent-index
        # autocommit blocks; do not wrap upgrades in an outer transaction.
        with engine.connect() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(test_engine: Engine) -> Iterator[Session]:
    with test_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            ) as session:
                yield session
        finally:
            transaction.rollback()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client


@pytest.fixture
def transfer_client(test_engine: Engine) -> Iterator[TestClient]:
    app = create_app()

    def fresh_session() -> Iterator[Session]:
        with Session(test_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = fresh_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def account_factory(test_engine: Engine) -> Iterator[Callable[..., list[UUID]]]:
    account_ids: list[UUID] = []

    def create(*balances: str) -> list[UUID]:
        with Session(test_engine, expire_on_commit=False) as session, session.begin():
            accounts = [
                Account(owner_name="Transfer test", balance=Decimal(balance))
                for balance in balances
            ]
            session.add_all(accounts)
            session.flush()
            ids = [account.id for account in accounts]
            account_ids.extend(ids)
            return ids

    try:
        yield create
    finally:
        if account_ids:
            with test_engine.begin() as connection:
                connection.execute(
                    delete(Transfer).where(
                        or_(
                            Transfer.source_account_id.in_(account_ids),
                            Transfer.destination_account_id.in_(account_ids),
                        )
                    )
                )
                connection.execute(delete(Account).where(Account.id.in_(account_ids)))
