from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

pytestmark = pytest.mark.integration


def test_upgrade_preserves_existing_data_and_downgrade_removes_only_additions(
    test_engine: Engine,
) -> None:
    # Exercise the real revision chain in a private schema, never downgrade public.
    schema_name = f"migration_test_{uuid4().hex}"
    source, destination, transfer_id = uuid4(), uuid4(), uuid4()
    with test_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')
        connection.exec_driver_sql(f'SET search_path TO "{schema_name}"')
        connection.commit()
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        try:
            command.upgrade(config, "0002")
            connection.execute(
                text(
                    "INSERT INTO accounts (id, owner_name, balance) "
                    "VALUES (:source, 'Existing source', 90), "
                    "(:destination, 'Existing destination', 10)"
                ),
                {"source": source, "destination": destination},
            )
            connection.execute(
                text(
                    "INSERT INTO transfers "
                    "(id, source_account_id, destination_account_id, amount, "
                    "idempotency_key) VALUES (:id, :source, :destination, 10, 'legacy')"
                ),
                {"id": transfer_id, "source": source, "destination": destination},
            )
            connection.commit()

            command.upgrade(config, "head")
            assert connection.scalar(
                text("SELECT balance FROM accounts WHERE id = :id"), {"id": source}
            ) == Decimal("90.00")
            assert (
                connection.scalar(
                    text("SELECT idempotency_key FROM transfers WHERE id = :id"),
                    {"id": transfer_id},
                )
                == "legacy"
            )
            indexes = {
                index["name"] for index in inspect(connection).get_indexes("transfers")
            }
            assert {
                "ix_transfers_source_history",
                "ix_transfers_destination_history",
            } <= indexes
            assert (
                connection.scalar(
                    text(
                        "SELECT convalidated FROM pg_constraint "
                        "WHERE conrelid = 'accounts'::regclass "
                        "AND conname = 'ck_accounts_balance_upper_bound'"
                    )
                )
                is True
            )
            connection.commit()

            command.downgrade(config, "0002")
            assert connection.scalar(text("SELECT count(*) FROM transfers")) == 1
            assert connection.scalar(text("SELECT count(*) FROM accounts")) == 2
            assert not any(
                index["name"].endswith("_history")
                for index in inspect(connection).get_indexes("transfers")
            )
        finally:
            connection.rollback()
            connection.exec_driver_sql("SET search_path TO public")
            connection.exec_driver_sql(f'DROP SCHEMA "{schema_name}" CASCADE')
            connection.commit()
