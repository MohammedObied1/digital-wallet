from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, default=None)
    attempted_username: Mapped[str | None] = mapped_column(String(50), default=None)
    event_type: Mapped[str] = mapped_column(String(30))  # login_success, login_failure, refresh, logout
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(255), default=None)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user: Mapped["User"] = relationship(back_populates="login_events")  # noqa: F821
