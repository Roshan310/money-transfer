"""Index account history and guard finite balances.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_transfers_source_history",
            "transfers",
            ["source_account_id", "created_at", "id"],
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_transfers_destination_history",
            "transfers",
            ["destination_account_id", "created_at", "id"],
            postgresql_concurrently=True,
        )
    op.create_check_constraint(
        "ck_accounts_balance_upper_bound",
        "accounts",
        "balance <= 9999999999999999.99",
        postgresql_not_valid=True,
    )


def downgrade() -> None:
    op.drop_constraint("ck_accounts_balance_upper_bound", "accounts", type_="check")
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_transfers_destination_history",
            "transfers",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_transfers_source_history", "transfers", postgresql_concurrently=True
        )
