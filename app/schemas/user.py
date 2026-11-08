import re

from pydantic import BaseModel, EmailStr, field_validator

from app.models.enums import UserRole

PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not PASSWORD_RE.match(v):
            raise ValueError("Password must be at least 8 characters and include a letter and a digit")
        return v

    @field_validator("username")
    @classmethod
    def username_format(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]{3,50}$", v):
            raise ValueError("Username must be 3-50 characters: letters, digits, underscore")
        return v


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    full_name: str | None
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None and not PASSWORD_RE.match(v):
            raise ValueError("Password must be at least 8 characters and include a letter and a digit")
        return v
