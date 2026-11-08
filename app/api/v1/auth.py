from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DBSession
from app.schemas.token import RefreshRequest, TokenPair
from app.schemas.user import UserOut, UserRegister
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserRegister, db: DBSession) -> UserOut:
    user = auth_service.register(db, data)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenPair)
def login(request: Request, db: DBSession, form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenPair:
    return auth_service.login(
        db,
        form.username,
        form.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshRequest, db: DBSession) -> TokenPair:
    return auth_service.refresh(db, data.refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
