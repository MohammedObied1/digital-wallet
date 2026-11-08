import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models import LoginEvent, User
from app.schemas.token import TokenPair
from app.schemas.user import UserRegister
from app.services import audit_service


def register(db: Session, data: UserRegister) -> User:
    if db.scalar(select(User).where(User.email == data.email)):
        raise ConflictError("Email already registered")
    if db.scalar(select(User).where(User.username == data.username)):
        raise ConflictError("Username already taken")

    user = User(
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    db.flush()
    audit_service.record(db, action="user.register", entity_type="user", entity_id=user.id, actor_user_id=user.id)
    db.commit()
    db.refresh(user)
    return user


def _tokens_for(user: User) -> TokenPair:
    subject = str(user.id)
    return TokenPair(access_token=create_access_token(subject), refresh_token=create_refresh_token(subject))


def login(db: Session, username: str, password: str, *, ip_address: str | None = None, user_agent: str | None = None) -> TokenPair:
    user = db.scalar(select(User).where(User.username == username))
    ok = bool(user) and verify_password(password, user.password_hash)

    db.add(
        LoginEvent(
            user_id=user.id if user else None,
            attempted_username=None if user else username,
            event_type="login_success" if ok else "login_failure",
            ip_address=ip_address,
            user_agent=user_agent,
            success=ok,
        )
    )
    if not ok or not user.is_active:
        db.commit()
        raise UnauthorizedError("Incorrect username or password")

    db.commit()
    return _tokens_for(user)


def refresh(db: Session, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired refresh token") from exc

    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    db.add(LoginEvent(user_id=user.id, event_type="refresh", success=True))
    db.commit()
    return _tokens_for(user)
