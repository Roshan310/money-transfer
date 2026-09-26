"""Validate the finite balance constraint without rewriting account data.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE accounts VALIDATE CONSTRAINT ck_accounts_balance_upper_bound"
    )


def downgrade() -> None:
    # The bound remains enforced until revision 0003 is also downgraded.
    pass
