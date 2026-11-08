from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import AdminUser, DBSession, PageParams, SupportUser
from app.core.exceptions import NotFoundError
from app.models import User
from app.schemas.user import UserOut
from app.services import audit_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=dict)
def list_users(db: DBSession, page: PageParams, _: SupportUser) -> dict:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = db.scalars(select(User).order_by(User.id).offset(page.offset).limit(page.size)).all()
    return page.build([UserOut.model_validate(u) for u in users], total)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: DBSession, _: SupportUser) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return UserOut.model_validate(user)


@router.post("/{user_id}/activate", response_model=UserOut)
def activate_user(user_id: int, db: DBSession, admin: AdminUser) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    before = {"is_active": user.is_active}
    user.is_active = True
    audit_service.record(
        db, action="user.activate", entity_type="user", entity_id=user.id, actor_user_id=admin.id, before=before, after={"is_active": True}
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: int, db: DBSession, admin: AdminUser) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    before = {"is_active": user.is_active}
    user.is_active = False
    audit_service.record(
        db,
        action="user.deactivate",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=admin.id,
        before=before,
        after={"is_active": False},
    )
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
