"""The financial transaction engine: deposit, withdraw, transfer, refund, reversal.

Every money-moving operation follows the same shape:
  1. Create the Transaction row (status=PENDING) and flush to get an id.
  2. Lock every wallet involved, in a fixed order (ledger_service.lock_wallets).
  3. Validate: wallets active, sufficient funds, transfer limits, fraud rules.
  4. Write ledger entries (ledger_service.apply_entries) — this is where money actually moves.
  5. Mark the transaction COMPLETED, enqueue an outbox notification event, write an audit log.
  6. Commit everything atomically (idempotency_service.commit_atomically).

If any validation step fails, nothing has been locked-and-abandoned incorrectly: the whole
SQLAlchemy session is rolled back by the caller (see api/v1/transactions.py), so a failed
transfer never partially applies.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, FraudBlockedError, NotFoundError
from app.models import (
    FraudAction,
    LedgerEntryType,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
    Wallet,
)
from app.services import audit_service, fraud_service, ledger_service, limits_service, outbox_service
from app.services.ledger_service import LedgerLine


def _new_transaction(db: Session, *, type_: TransactionType, amount: Decimal, currency: str, **kwargs) -> Transaction:
    # Quantized explicitly rather than relying on a DB round-trip to normalize it: the API
    # response for a freshly-created transaction is built from this in-memory object before it's
    # ever re-read from the database, so without this an amount like `Decimal("200")` (valid,
    # e.g. from a JSON int) would render as "200" instead of "200.00" in that one response, while
    # every *subsequent* GET of the same row (which does round-trip through NUMERIC(18,2)) would
    # correctly show "200.00" — a purely cosmetic but confusing inconsistency.
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    amount = amount.quantize(Decimal("0.01"))
    txn = Transaction(type=type_, status=TransactionStatus.PENDING, amount=amount, currency=currency, **kwargs)
    db.add(txn)
    db.flush()
    return txn


def _fail_and_commit(db: Session, txn: Transaction, actor: User, exc: Exception) -> None:
    """A failed transaction still needs to exist for the audit trail and fraud dashboard — commit
    the FAILED Transaction row, its FraudEvent rows if any (no ledger entries were written, so no
    money moved), and an audit log entry before raising. Otherwise the whole request's rollback
    would erase the evidence that the attempt ever happened — see the "Transfer failure" audit
    event required by ARCHITECTURE.md's audit logging section.
    """
    txn.status = TransactionStatus.FAILED
    audit_service.record(
        db,
        action=f"transaction.{txn.type.value}.failed",
        entity_type="transaction",
        entity_id=txn.id,
        actor_user_id=actor.id,
        after={"reason": str(exc)},
    )
    db.commit()
    raise exc


def _finalize(db: Session, txn: Transaction) -> None:
    txn.status = TransactionStatus.COMPLETED
    txn.completed_at = datetime.now(UTC)
    outbox_service.enqueue(
        db,
        f"transaction.{txn.type.value}.completed",
        {
            "transaction_id": txn.id,
            "type": txn.type.value,
            "amount": float(txn.amount),
            "currency": txn.currency,
            "sender_wallet_id": txn.sender_wallet_id,
            "receiver_wallet_id": txn.receiver_wallet_id,
        },
    )


def deposit(db: Session, wallet: Wallet, amount: Decimal, description: str | None, actor: User) -> Transaction:
    txn = _new_transaction(
        db,
        type_=TransactionType.DEPOSIT,
        amount=amount,
        currency=wallet.currency.value,
        receiver_wallet_id=wallet.id,
        description=description,
    )
    try:
        locked = ledger_service.lock_wallets(db, [wallet.id])
        ledger_service.require_active(locked[wallet.id])
        ledger_service.apply_entries(db, txn, locked, [LedgerLine(wallet.id, LedgerEntryType.CREDIT, amount)])
    except AppException as exc:
        _fail_and_commit(db, txn, actor, exc)

    _finalize(db, txn)
    audit_service.record(db, action="transaction.deposit", entity_type="transaction", entity_id=txn.id, actor_user_id=actor.id)
    return txn


def withdraw(db: Session, wallet: Wallet, amount: Decimal, description: str | None, actor: User) -> Transaction:
    txn = _new_transaction(
        db,
        type_=TransactionType.WITHDRAWAL,
        amount=amount,
        currency=wallet.currency.value,
        sender_wallet_id=wallet.id,
        description=description,
    )
    try:
        locked = ledger_service.lock_wallets(db, [wallet.id])
        fresh_wallet = locked[wallet.id]
        ledger_service.require_active(fresh_wallet)
        limits_service.check_transaction_limits(db, fresh_wallet, actor, amount, TransactionType.WITHDRAWAL)

        action, events = fraud_service.evaluate(
            db, amount=amount, txn_type=TransactionType.WITHDRAWAL, sender_wallet_id=wallet.id, receiver_wallet_id=None, sender=actor
        )
        _attach_fraud_events(db, txn, events)
        if action == FraudAction.BLOCK:
            raise FraudBlockedError()

        ledger_service.apply_entries(db, txn, locked, [LedgerLine(wallet.id, LedgerEntryType.DEBIT, amount)])
    except AppException as exc:
        _fail_and_commit(db, txn, actor, exc)

    _finalize(db, txn)
    audit_service.record(db, action="transaction.withdraw", entity_type="transaction", entity_id=txn.id, actor_user_id=actor.id)
    return txn


def transfer(
    db: Session, sender_wallet: Wallet, receiver_wallet: Wallet, amount: Decimal, description: str | None, actor: User
) -> Transaction:
    if sender_wallet.id == receiver_wallet.id:
        raise NotFoundError("Cannot transfer a wallet to itself")
    if sender_wallet.currency != receiver_wallet.currency:
        raise FraudBlockedError("Cross-currency transfers are not supported yet")

    txn = _new_transaction(
        db,
        type_=TransactionType.TRANSFER,
        amount=amount,
        currency=sender_wallet.currency.value,
        sender_wallet_id=sender_wallet.id,
        receiver_wallet_id=receiver_wallet.id,
        description=description,
    )

    try:
        locked = ledger_service.lock_wallets(db, [sender_wallet.id, receiver_wallet.id])
        fresh_sender, fresh_receiver = locked[sender_wallet.id], locked[receiver_wallet.id]
        ledger_service.require_active(fresh_sender)
        ledger_service.require_active(fresh_receiver)
        limits_service.check_transaction_limits(db, fresh_sender, actor, amount, TransactionType.TRANSFER)

        action, events = fraud_service.evaluate(
            db,
            amount=amount,
            txn_type=TransactionType.TRANSFER,
            sender_wallet_id=sender_wallet.id,
            receiver_wallet_id=receiver_wallet.id,
            sender=actor,
        )
        _attach_fraud_events(db, txn, events)
        if action == FraudAction.BLOCK:
            raise FraudBlockedError()

        ledger_service.apply_entries(
            db,
            txn,
            locked,
            [
                LedgerLine(sender_wallet.id, LedgerEntryType.DEBIT, amount),
                LedgerLine(receiver_wallet.id, LedgerEntryType.CREDIT, amount),
            ],
        )
    except AppException as exc:
        _fail_and_commit(db, txn, actor, exc)

    _finalize(db, txn)
    audit_service.record(db, action="transaction.transfer", entity_type="transaction", entity_id=txn.id, actor_user_id=actor.id)
    return txn


def refund(db: Session, original: Transaction, actor: User, amount: Decimal | None = None) -> Transaction:
    """Refund a completed transfer or deposit, moving funds back from the receiver to the sender
    (for a transfer) or debiting the depositor's wallet (for a deposit). Defaults to a full refund.
    """
    if original.type == TransactionType.TRANSFER:
        from_wallet_id, to_wallet_id = original.receiver_wallet_id, original.sender_wallet_id
    else:  # DEPOSIT: pull the money back out of the wallet that received it
        from_wallet_id, to_wallet_id = original.receiver_wallet_id, None

    wallet_ids = [w for w in (from_wallet_id, to_wallet_id) if w is not None]
    locked = ledger_service.lock_wallets(db, wallet_ids)
    for wallet in locked.values():
        ledger_service.require_active(wallet)

    # Re-fetch `original` under FOR UPDATE now that the wallets are locked too — see
    # lock_transaction's docstring for why the caller's earlier, pre-lock copy isn't trustworthy.
    original = ledger_service.lock_transaction(db, original.id)
    if original.status != TransactionStatus.COMPLETED:
        raise FraudBlockedError("Only completed transactions can be refunded")
    if original.type not in (TransactionType.TRANSFER, TransactionType.DEPOSIT):
        raise FraudBlockedError("Only transfers and deposits can be refunded")

    refund_amount = amount if amount is not None else original.amount
    if refund_amount <= 0 or refund_amount > original.amount:
        raise FraudBlockedError("Refund amount must be positive and not exceed the original amount")

    txn = _new_transaction(
        db,
        type_=TransactionType.REFUND,
        amount=refund_amount,
        currency=original.currency,
        sender_wallet_id=from_wallet_id,
        receiver_wallet_id=to_wallet_id,
        description=f"Refund of transaction #{original.id}",
        related_transaction_id=original.id,
    )
    lines = [LedgerLine(from_wallet_id, LedgerEntryType.DEBIT, refund_amount)]
    if to_wallet_id is not None:
        lines.append(LedgerLine(to_wallet_id, LedgerEntryType.CREDIT, refund_amount))
    ledger_service.apply_entries(db, txn, locked, lines)
    _finalize(db, txn)

    if refund_amount == original.amount:
        original.status = TransactionStatus.REFUNDED
    audit_service.record(db, action="transaction.refund", entity_type="transaction", entity_id=txn.id, actor_user_id=actor.id)
    return txn


def reverse(db: Session, original: Transaction, actor: User) -> Transaction:
    """Fully reverse a completed transaction by writing the exact opposite ledger entries.
    Unlike refund (a new transaction the receiver/sender agreed to), reversal is an
    administrative correction — e.g. a transaction that should never have completed.
    """
    wallet_ids = [w for w in (original.sender_wallet_id, original.receiver_wallet_id) if w is not None]
    locked = ledger_service.lock_wallets(db, wallet_ids)
    for wallet in locked.values():
        ledger_service.require_active(wallet)

    # See refund()'s identical comment: re-fetch under FOR UPDATE after the wallet locks so two
    # concurrent reversal requests for the same transaction can't both see COMPLETED and both apply.
    original = ledger_service.lock_transaction(db, original.id)
    if original.status != TransactionStatus.COMPLETED:
        raise FraudBlockedError("Only completed transactions can be reversed")

    txn = _new_transaction(
        db,
        type_=TransactionType.REVERSAL,
        amount=original.amount,
        currency=original.currency,
        sender_wallet_id=original.receiver_wallet_id,
        receiver_wallet_id=original.sender_wallet_id,
        description=f"Reversal of transaction #{original.id}",
        related_transaction_id=original.id,
    )
    lines = []
    if original.receiver_wallet_id is not None:
        lines.append(LedgerLine(original.receiver_wallet_id, LedgerEntryType.DEBIT, original.amount))
    if original.sender_wallet_id is not None:
        lines.append(LedgerLine(original.sender_wallet_id, LedgerEntryType.CREDIT, original.amount))
    ledger_service.apply_entries(db, txn, locked, lines)
    _finalize(db, txn)

    original.status = TransactionStatus.REVERSED
    audit_service.record(db, action="transaction.reverse", entity_type="transaction", entity_id=txn.id, actor_user_id=actor.id)
    return txn


def _attach_fraud_events(db: Session, txn: Transaction, events: list) -> None:
    for event in events:
        event.transaction_id = txn.id
        db.add(event)
