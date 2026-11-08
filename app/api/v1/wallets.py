from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import AdminUser, CurrentUser, DBSession, PageParams, SupportUser
from app.models import Wallet, WalletStatus
from app.models.enums import Currency
from app.schemas.wallet import WalletCreate, WalletOut
from app.services import wallet_service

router = APIRouter(prefix="/wallets", tags=["Wallets"])


@router.post("", response_model=WalletOut, status_code=201)
def create_wallet(data: WalletCreate, db: DBSession, user: CurrentUser) -> WalletOut:
    wallet = wallet_service.create_wallet(db, user, data)
    return WalletOut.model_validate(wallet)


@router.get("", response_model=list[WalletOut])
def list_my_wallets(db: DBSession, user: CurrentUser) -> list[WalletOut]:
    wallets = wallet_service.list_my_wallets(db, user)
    return [WalletOut.model_validate(w) for w in wallets]


@router.get("/search", response_model=dict)
def search_wallets(
    db: DBSession,
    page: PageParams,
    _: SupportUser,
    user_id: int | None = None,
    status: WalletStatus | None = None,
    currency: Currency | None = None,
) -> dict:
    """Admin/support wallet explorer — search across every user's wallets."""
    stmt = select(Wallet)
    if user_id is not None:
        stmt = stmt.where(Wallet.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Wallet.status == status)
    if currency is not None:
        stmt = stmt.where(Wallet.currency == currency)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Wallet.id.desc()).offset(page.offset).limit(page.size)).all()
    return page.build([WalletOut.model_validate(w) for w in rows], total)


@router.get("/{wallet_id}", response_model=WalletOut)
def get_wallet(wallet_id: int, db: DBSession, user: CurrentUser) -> WalletOut:
    wallet = wallet_service.get_wallet_for_owner(db, wallet_id, user)
    return WalletOut.model_validate(wallet)


@router.post("/{wallet_id}/freeze", response_model=WalletOut)
def freeze_wallet(wallet_id: int, db: DBSession, admin: AdminUser) -> WalletOut:
    wallet = wallet_service.freeze_wallet(db, wallet_id, admin)
    return WalletOut.model_validate(wallet)


@router.post("/{wallet_id}/unfreeze", response_model=WalletOut)
def unfreeze_wallet(wallet_id: int, db: DBSession, admin: AdminUser) -> WalletOut:
    wallet = wallet_service.unfreeze_wallet(db, wallet_id, admin)
    return WalletOut.model_validate(wallet)
