from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class TransferLimitPolicy(Base, TimestampMixin):
    """A configurable limit policy. `scope` is 'global', 'role', or 'user'; `scope_ref` holds the
    role name or user id it applies to (null for 'global'). The most specific active policy that
    matches a user wins; falls back to settings.DEFAULT_* when no policy row matches.
    """

    __tablename__ = "transfer_limit_policies"
    __table_args__ = (
        # A NULL scope_ref (the 'global' policy) does not participate in a UNIQUE constraint under
        # standard SQL semantics (NULLs are never equal), so this only actually de-duplicates
        # role/user-scoped policies — enforcing "at most one global policy" is left to the service
        # layer, which always queries for the single active one.
        UniqueConstraint("scope", "scope_ref", name="uq_limit_policy_scope"),
        CheckConstraint("max_transaction_amount > 0", name="ck_limit_max_txn_positive"),
        CheckConstraint("daily_transfer_limit > 0", name="ck_limit_daily_transfer_positive"),
        CheckConstraint("daily_withdrawal_limit > 0", name="ck_limit_daily_withdrawal_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))
    scope_ref: Mapped[str | None] = mapped_column(String(50), default=None)
    max_transaction_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    daily_transfer_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    daily_withdrawal_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
