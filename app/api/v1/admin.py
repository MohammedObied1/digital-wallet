from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DBSession, SupportUser
from app.models import FraudAction, FraudEvent, Transaction, TransactionStatus, User, Wallet, WalletStatus

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
def stats(db: DBSession, _: SupportUser) -> dict:
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    active_wallets = db.scalar(select(func.count()).where(Wallet.status == WalletStatus.ACTIVE)) or 0

    by_status = dict(db.execute(select(Transaction.status, func.count()).group_by(Transaction.status)).all())
    by_type = dict(db.execute(select(Transaction.type, func.count()).group_by(Transaction.type)).all())

    completed_volume = (
        db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.status == TransactionStatus.COMPLETED)) or 0
    )
    fraud_review_count = db.scalar(select(func.count()).where(FraudEvent.action == FraudAction.REVIEW)) or 0
    fraud_block_count = db.scalar(select(func.count()).where(FraudEvent.action == FraudAction.BLOCK)) or 0

    return {
        "total_users": total_users,
        "active_wallets": active_wallets,
        "transactions_by_status": {k.value if hasattr(k, "value") else k: v for k, v in by_status.items()},
        "transactions_by_type": {k.value if hasattr(k, "value") else k: v for k, v in by_type.items()},
        "completed_transaction_volume": float(completed_volume),
        "fraud_review_count": fraud_review_count,
        "fraud_block_count": fraud_block_count,
    }
