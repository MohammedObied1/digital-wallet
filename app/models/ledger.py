from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import LedgerEntryType


class LedgerEntry(Base):
    """Append-only. Never updated, never deleted. The source of truth for wallet balances."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_wallet_created", "wallet_id", "created_at"),
        CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        CheckConstraint("balance_after >= 0", name="ck_ledger_balance_after_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    entry_type: Mapped[LedgerEntryType] = mapped_column(Enum(LedgerEntryType, native_enum=False, length=10))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(10))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    wallet: Mapped["Wallet"] = relationship()  # noqa: F821
    transaction: Mapped["Transaction"] = relationship(back_populates="ledger_entries")  # noqa: F821
