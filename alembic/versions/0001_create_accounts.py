"""Create accounts.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_name", sa.String(100), nullable=False),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("balance >= 0", name="ck_accounts_balance_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
    )


def downgrade() -> None:
    op.drop_table("accounts")
