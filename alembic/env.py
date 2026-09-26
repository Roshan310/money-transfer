from alembic import context
from sqlalchemy import Connection

from app.accounts.models import Account  # noqa: F401
from app.database import Base, get_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    from app.config import get_settings

    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests may supply a connection to their dedicated database.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        run_with_connection(connection)
    else:
        with get_engine().connect() as connection:
            run_with_connection(connection)


def run_with_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
