"""A small, configurable fraud/risk rules engine.

Each active FraudRule is evaluated against the transaction being processed. The highest-severity
action wins (BLOCK > REVIEW > ALLOW). A BLOCK stops the transaction (FraudBlockedError, caught by
the caller before any ledger write happens). A REVIEW lets the transaction complete but records a
FraudEvent for the admin fraud dashboard (Step 12). Rule outcomes are always logged as FraudEvent
rows, even ALLOW, so risk analysts can see what was evaluated.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FraudAction, FraudEvent, FraudRule, Transaction, TransactionStatus, TransactionType, User

_ACTION_SEVERITY = {FraudAction.ALLOW: 0, FraudAction.REVIEW: 1, FraudAction.BLOCK: 2}


def _large_amount(rule: FraudRule, *, amount: Decimal, **_: Any) -> bool:
    return amount >= Decimal(str(rule.config.get("threshold", 5000)))


def _velocity(rule: FraudRule, *, db: Session, sender_wallet_id: int | None, **_: Any) -> bool:
    if sender_wallet_id is None:
        return False
    window = timedelta(minutes=int(rule.config.get("window_minutes", 10)))
    max_count = int(rule.config.get("max_transactions", 5))
    since = datetime.now(UTC) - window
    count = db.scalar(
        select(func.count()).where(
            Transaction.sender_wallet_id == sender_wallet_id,
            Transaction.created_at >= since,
        )
    )
    return (count or 0) >= max_count


def _new_recipient(
    rule: FraudRule, *, db: Session, amount: Decimal, sender_wallet_id: int | None, receiver_wallet_id: int | None, **_: Any
) -> bool:
    if sender_wallet_id is None or receiver_wallet_id is None:
        return False
    min_amount = Decimal(str(rule.config.get("min_amount", 1000)))
    if amount < min_amount:
        return False
    prior = db.scalar(
        select(func.count()).where(
            Transaction.sender_wallet_id == sender_wallet_id,
            Transaction.receiver_wallet_id == receiver_wallet_id,
            Transaction.status == TransactionStatus.COMPLETED,
        )
    )
    return (prior or 0) == 0


_EVALUATORS = {
    "large_amount": _large_amount,
    "transfer_velocity": _velocity,
    "new_recipient_large_amount": _new_recipient,
}


def evaluate(
    db: Session,
    *,
    amount: Decimal,
    txn_type: TransactionType,
    sender_wallet_id: int | None,
    receiver_wallet_id: int | None,
    sender: User | None,
) -> tuple[FraudAction, list[FraudEvent]]:
    rules = db.scalars(select(FraudRule).where(FraudRule.is_active.is_(True))).all()
    events: list[FraudEvent] = []
    worst_action = FraudAction.ALLOW

    for rule in rules:
        evaluator = _EVALUATORS.get(rule.rule_type)
        if evaluator is None:
            continue
        triggered = evaluator(
            rule,
            db=db,
            amount=amount,
            txn_type=txn_type,
            sender_wallet_id=sender_wallet_id,
            receiver_wallet_id=receiver_wallet_id,
            sender=sender,
        )
        if not triggered:
            continue
        action = rule.action
        events.append(
            FraudEvent(
                transaction_id=None,  # set by the caller once the Transaction row has an id
                rule_id=rule.id,
                risk_score=100.0 if action == FraudAction.BLOCK else 60.0 if action == FraudAction.REVIEW else 10.0,
                action=action,
                # float(), not amount directly: `details` is a JSON column, and Decimal isn't
                # JSON-serializable — this is a display value for the fraud dashboard, not a
                # source of financial truth (the Transaction/LedgerEntry rows hold that as Decimal).
                details={"rule": rule.name, "rule_type": rule.rule_type, "amount": float(amount)},
            )
        )
        if _ACTION_SEVERITY[action] > _ACTION_SEVERITY[worst_action]:
            worst_action = action

    return worst_action, events
