from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import TransactionStatus, TransactionType


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_txn_sender_created", "sender_wallet_id", "created_at"),
        Index("ix_txn_receiver_created", "receiver_wallet_id", "created_at"),
        CheckConstraint("amount > 0", name="ck_txn_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, native_enum=False, length=20))
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, native_enum=False, length=20), default=TransactionStatus.PENDING
    )
    sender_wallet_id: Mapped[int | None] = mapped_column(ForeignKey("wallets.id"), index=True, default=None)
    receiver_wallet_id: Mapped[int | None] = mapped_column(ForeignKey("wallets.id"), index=True, default=None)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    reference: Mapped[str | None] = mapped_column(String(100), default=None)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, default=None)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), index=True, default=None)
    related_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    sender_wallet: Mapped["Wallet | None"] = relationship(foreign_keys=[sender_wallet_id])  # noqa: F821
    receiver_wallet: Mapped["Wallet | None"] = relationship(foreign_keys=[receiver_wallet_id])  # noqa: F821
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="transaction")  # noqa: F821
