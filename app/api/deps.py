from typing import Annotated

import jwt
from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.models import User, UserRole

DBSession = Annotated[Session, Depends(get_db)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


def get_current_user(db: DBSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError() from exc
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Admin privileges required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def require_support_or_admin(user: CurrentUser) -> User:
    if user.role not in (UserRole.SUPPORT, UserRole.ADMIN):
        raise ForbiddenError("Support or admin privileges required")
    return user


SupportUser = Annotated[User, Depends(require_support_or_admin)]


class Pagination:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=settings.MAX_PAGE_SIZE)] = settings.DEFAULT_PAGE_SIZE,
    ) -> None:
        self.page = page
        self.size = size
        self.offset = (page - 1) * size

    def build(self, items: list, total: int) -> dict:
        return {"items": items, "total": total, "page": self.page, "size": self.size, "pages": max(1, -(-total // self.size))}


PageParams = Annotated[Pagination, Depends()]
