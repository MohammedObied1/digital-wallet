from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IdempotencyRecord(Base):
    """One row per (user_id, idempotency_key, endpoint). A retried request with the same key and
    the same body replays `response_body`/`status_code` instead of re-executing the operation.
    A retried request with the same key but a *different* body is rejected (IdempotencyConflictError).

    Scoped by `user_id`, not just (idempotency_key, endpoint): idempotency keys are client-chosen
    strings (often short-lived UUIDs, but nothing stops a client from reusing a predictable one).
    Without the user scope, user A could submit a request with the same Idempotency-Key user B
    happens to be using on the same endpoint and either get a spurious 409 conflict or — if the
    request bodies happened to hash the same — receive B's cached response. Scoping by user closes
    that cross-user leak entirely, at the cost of nothing (a client only ever needs their own keys
    to be unique to themselves).
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", "endpoint", name="uq_idempotency_user_key_endpoint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), index=True)
    endpoint: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
