from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import PaymentRequestStatus


class PaymentRequest(Base, TimestampMixin):
    __tablename__ = "payment_requests"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_request_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    payer_wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(10))
    status: Mapped[PaymentRequestStatus] = mapped_column(
        Enum(PaymentRequestStatus, native_enum=False, length=20), default=PaymentRequestStatus.PENDING
    )
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)

    requester_wallet: Mapped["Wallet"] = relationship(foreign_keys=[requester_wallet_id])  # noqa: F821
    payer_wallet: Mapped["Wallet"] = relationship(foreign_keys=[payer_wallet_id])  # noqa: F821
