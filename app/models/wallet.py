from decimal import Decimal

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import Currency, WalletStatus


class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_wallet_user_currency"),
        CheckConstraint("balance >= 0", name="ck_wallet_balance_non_negative"),
        CheckConstraint("available_balance >= 0", name="ck_wallet_available_balance_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    currency: Mapped[Currency] = mapped_column(Enum(Currency, native_enum=False, length=10))
    status: Mapped[WalletStatus] = mapped_column(Enum(WalletStatus, native_enum=False, length=20), default=WalletStatus.ACTIVE)

    # Cached, denormalized for fast reads. The ledger (ledger_entries) is the source of truth;
    # these two columns must always be reproducible by summing this wallet's ledger entries.
    # `asdecimal` is intentionally left at its default (True): money is never represented as a
    # Python float anywhere in this codebase — see ARCHITECTURE.md's "Money representation" section.
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    # Optimistic-lock counter for non-critical concurrent reads/writes (e.g. admin freeze racing
    # a transfer). The transfer path itself relies on SELECT ... FOR UPDATE, not this column.
    version: Mapped[int] = mapped_column(default=0)

    label: Mapped[str | None] = mapped_column(String(100), default=None)

    user: Mapped["User"] = relationship(back_populates="wallets")  # noqa: F821
