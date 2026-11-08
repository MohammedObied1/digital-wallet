from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import OutboxStatus


class OutboxEvent(Base):
    """Written in the SAME DB transaction as the financial change it describes (transactional
    outbox pattern). A separate worker (workers/outbox_worker.py) polls for `pending` rows and
    dispatches them — this is how notifications happen without being sent inside the financial
    transaction itself.
    """

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus, native_enum=False, length=10), default=OutboxStatus.PENDING, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
