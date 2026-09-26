from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_accounts_balance_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_name: Mapped[str] = mapped_column(String(100))
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
