from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor_user_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Insert an immutable audit row. Callers must not update or delete audit rows — there is
    intentionally no service function to do so.
    """
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry
