from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import User, UserRole, Wallet, WalletStatus
from app.schemas.wallet import WalletCreate
from app.services import audit_service


def create_wallet(db: Session, user: User, data: WalletCreate) -> Wallet:
    existing = db.scalar(select(Wallet).where(Wallet.user_id == user.id, Wallet.currency == data.currency))
    if existing:
        raise ConflictError(f"You already have a {data.currency.value} wallet")

    wallet = Wallet(user_id=user.id, currency=data.currency, label=data.label, balance=0, available_balance=0)
    db.add(wallet)
    db.flush()
    audit_service.record(db, action="wallet.create", entity_type="wallet", entity_id=wallet.id, actor_user_id=user.id)
    db.commit()
    db.refresh(wallet)
    return wallet


def get_wallet_for_owner(db: Session, wallet_id: int, user: User) -> Wallet:
    wallet = db.get(Wallet, wallet_id)
    if not wallet:
        raise NotFoundError("Wallet not found")
    if wallet.user_id != user.id and user.role not in (UserRole.SUPPORT, UserRole.ADMIN):
        raise NotFoundError("Wallet not found")
    return wallet


def get_wallet_by_id(db: Session, wallet_id: int) -> Wallet:
    """Fetch any wallet by id, regardless of ownership — used for the *receiver* side of a
    transfer, where the sender is picking someone else's wallet on purpose.
    """
    wallet = db.get(Wallet, wallet_id)
    if not wallet:
        raise NotFoundError("Wallet not found")
    return wallet


def list_my_wallets(db: Session, user: User) -> list[Wallet]:
    return list(db.scalars(select(Wallet).where(Wallet.user_id == user.id).order_by(Wallet.id)))


def _set_status(db: Session, wallet_id: int, status: WalletStatus, actor: User, action: str) -> Wallet:
    wallet = db.get(Wallet, wallet_id)
    if not wallet:
        raise NotFoundError("Wallet not found")
    before = {"status": wallet.status.value}
    wallet.status = status
    wallet.version += 1
    audit_service.record(
        db, action=action, entity_type="wallet", entity_id=wallet.id, actor_user_id=actor.id, before=before, after={"status": status.value}
    )
    db.commit()
    db.refresh(wallet)
    return wallet


def freeze_wallet(db: Session, wallet_id: int, admin: User) -> Wallet:
    return _set_status(db, wallet_id, WalletStatus.FROZEN, admin, "wallet.freeze")


def unfreeze_wallet(db: Session, wallet_id: int, admin: User) -> Wallet:
    return _set_status(db, wallet_id, WalletStatus.ACTIVE, admin, "wallet.unfreeze")
