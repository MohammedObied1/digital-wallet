"""Configurable transfer/withdrawal limits.

Resolution order for a user: an active 'user'-scoped policy > an active 'role'-scoped policy for
their role > the 'global' active policy > the hardcoded settings.DEFAULT_* values. This lets
support/admin tune limits per user (e.g. after a fraud review) without a deploy.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import TransferLimitExceededError
from app.models import Transaction, TransactionStatus, TransactionType, TransferLimitPolicy, User, Wallet


def _resolve_policy(db: Session, user: User) -> tuple[Decimal, Decimal, Decimal]:
    for scope, ref in (("user", str(user.id)), ("role", user.role.value), ("global", None)):
        stmt = select(TransferLimitPolicy).where(TransferLimitPolicy.scope == scope, TransferLimitPolicy.is_active.is_(True))
        stmt = stmt.where(TransferLimitPolicy.scope_ref == ref) if ref is not None else stmt.where(TransferLimitPolicy.scope_ref.is_(None))
        policy = db.scalar(stmt)
        if policy:
            return policy.max_transaction_amount, policy.daily_transfer_limit, policy.daily_withdrawal_limit
    return settings.DEFAULT_MAX_TRANSACTION_AMOUNT, settings.DEFAULT_DAILY_TRANSFER_LIMIT, settings.DEFAULT_DAILY_WITHDRAWAL_LIMIT


def _completed_today_total(db: Session, wallet_id: int, txn_type: TransactionType) -> Decimal:
    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    total = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.sender_wallet_id == wallet_id,
            Transaction.type == txn_type,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= start_of_day,
        )
    )
    return Decimal(str(total or 0))


def check_transaction_limits(db: Session, wallet: Wallet, user: User, amount: Decimal, txn_type: TransactionType) -> None:
    max_amount, daily_transfer_limit, daily_withdrawal_limit = _resolve_policy(db, user)

    if amount > max_amount:
        raise TransferLimitExceededError(f"Amount {amount} exceeds the maximum per-transaction limit of {max_amount}")

    if txn_type == TransactionType.TRANSFER:
        used = _completed_today_total(db, wallet.id, TransactionType.TRANSFER)
        if used + amount > daily_transfer_limit:
            raise TransferLimitExceededError(f"Daily transfer limit of {daily_transfer_limit} exceeded (already sent {used} today)")
    elif txn_type == TransactionType.WITHDRAWAL:
        used = _completed_today_total(db, wallet.id, TransactionType.WITHDRAWAL)
        if used + amount > daily_withdrawal_limit:
            raise TransferLimitExceededError(
                f"Daily withdrawal limit of {daily_withdrawal_limit} exceeded (already withdrawn {used} today)"
            )
