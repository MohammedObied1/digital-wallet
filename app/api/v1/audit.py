from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import AdminUser, DBSession, PageParams
from app.models import AuditLog
from app.schemas.audit import AuditLogOut

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=dict)
def search_audit_log(
    db: DBSession,
    page: PageParams,
    _: AdminUser,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor_user_id: int | None = None,
) -> dict:
    stmt = select(AuditLog)
    if entity_type is not None:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).offset(page.offset).limit(page.size)).all()
    return page.build([AuditLogOut.model_validate(r) for r in rows], total)
