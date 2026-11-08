from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import UserRole


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255), default=None)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=20), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    wallets: Mapped[list["Wallet"]] = relationship(back_populates="user")  # noqa: F821
    login_events: Mapped[list["LoginEvent"]] = relationship(back_populates="user")  # noqa: F821
