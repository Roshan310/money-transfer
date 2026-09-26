from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_transfers_idempotency_key"),
        CheckConstraint(
            "amount > 0 AND amount <= 9999999999999999.99",
            name="ck_transfers_amount_range",
        ),
        CheckConstraint(
            "source_account_id != destination_account_id",
            name="ck_transfers_distinct_accounts",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", name="fk_transfers_source_account_id")
    )
    destination_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", name="fk_transfers_destination_account_id")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
