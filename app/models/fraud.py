from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import FraudAction


class FraudRule(Base, TimestampMixin):
    __tablename__ = "fraud_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    rule_type: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[FraudAction] = mapped_column(Enum(FraudAction, native_enum=False, length=10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FraudEvent(Base):
    __tablename__ = "fraud_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("fraud_rules.id"), default=None)
    risk_score: Mapped[float] = mapped_column(Numeric(5, 2, asdecimal=False))
    action: Mapped[FraudAction] = mapped_column(Enum(FraudAction, native_enum=False, length=10))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    rule: Mapped["FraudRule | None"] = relationship()
    transaction: Mapped["Transaction"] = relationship()  # noqa: F821
