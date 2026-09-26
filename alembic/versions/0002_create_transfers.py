"""Create transfers with persistent idempotency keys.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transfers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_account_id", sa.Uuid(), nullable=False),
        sa.Column("destination_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transfers"),
        sa.UniqueConstraint("idempotency_key", name="uq_transfers_idempotency_key"),
        sa.ForeignKeyConstraint(
            ["source_account_id"],
            ["accounts.id"],
            name="fk_transfers_source_account_id",
        ),
        sa.ForeignKeyConstraint(
            ["destination_account_id"],
            ["accounts.id"],
            name="fk_transfers_destination_account_id",
        ),
        sa.CheckConstraint(
            "amount > 0 AND amount <= 9999999999999999.99",
            name="ck_transfers_amount_range",
        ),
        sa.CheckConstraint(
            "source_account_id != destination_account_id",
            name="ck_transfers_distinct_accounts",
        ),
    )


def downgrade() -> None:
    op.drop_table("transfers")
