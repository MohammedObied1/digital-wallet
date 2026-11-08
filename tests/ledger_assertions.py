"""Reusable ledger-integrity assertions shared across the test suite.

These encode the invariants a double-entry ledger must never violate, independent of which
scenario produced the data: every wallet's cached balance must be reproducible purely from its
ledger entries, and the ledger must be globally balanced (every debit has a matching credit).
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LedgerEntry, LedgerEntryType, Transaction, Wallet
from app.services import ledger_service


def assert_wallet_matches_ledger(db: Session, wallet_id: int) -> Decimal:
    """Assert `wallets.balance` equals the balance rebuilt purely from `ledger_entries`, and
    return that balance. Fails loudly (naming the wallet) rather than a bare `assert a == b`.
    """
    wallet = db.get(Wallet, wallet_id)
    rebuilt = ledger_service.rebuild_balance(db, wallet_id)
    assert wallet.balance == rebuilt, f"wallet {wallet_id}: cached balance {wallet.balance} != ledger-derived balance {rebuilt}"
    return rebuilt


def assert_transaction_is_balanced(db: Session, transaction_id: int) -> None:
    """Assert sum(debits) == sum(credits) *for one transaction's own ledger entries*.

    This only makes sense for internal movements (transfer, refund, reversal) where money moves
    from one of our wallets to another. Deposits and withdrawals are intentionally single-sided:
    they represent money crossing the system boundary (a simulated external bank/card network),
    and this system has no "external" wallet row to book the other side against — see
    ARCHITECTURE.md's "Money representation & ledger model" section. Calling this on a deposit or
    withdrawal transaction id will correctly fail; that is not a bug in the assertion.
    """
    debits = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.transaction_id == transaction_id, LedgerEntry.entry_type == LedgerEntryType.DEBIT
        )
    )
    credits = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.transaction_id == transaction_id, LedgerEntry.entry_type == LedgerEntryType.CREDIT
        )
    )
    assert Decimal(str(debits)) == Decimal(str(credits)), f"transaction {transaction_id} unbalanced: debits={debits} credits={credits}"


def assert_internal_transfers_balanced(db: Session) -> None:
    """Assert every transfer/refund/reversal transaction (the internal, two-sided movements) is
    individually balanced. Does not include deposits/withdrawals — see
    `assert_transaction_is_balanced`'s docstring for why those are excluded by design.
    """
    from app.models import Transaction, TransactionType

    ids = db.scalars(
        select(Transaction.id).where(Transaction.type.in_([TransactionType.TRANSFER, TransactionType.REFUND, TransactionType.REVERSAL]))
    )
    for transaction_id in ids:
        assert_transaction_is_balanced(db, transaction_id)


def assert_no_orphan_ledger_entries(db: Session) -> None:
    """Every ledger entry must reference a transaction that actually exists. Foreign keys already
    enforce this at the database layer; this assertion exists so a regression surfaces as a clear
    test failure here instead of a generic IntegrityError somewhere unrelated.
    """
    orphans = db.scalar(
        select(func.count())
        .select_from(LedgerEntry)
        .outerjoin(Transaction, LedgerEntry.transaction_id == Transaction.id)
        .where(Transaction.id.is_(None))
    )
    assert orphans == 0, f"{orphans} ledger entries reference a nonexistent transaction"


def assert_transaction_ledger_entry_count(db: Session, transaction_id: int, expected: int) -> None:
    """Assert a transaction produced exactly `expected` ledger entries — the guard against a
    retried/duplicated write silently doubling up entries for the same transaction.
    """
    count = db.scalar(select(func.count()).where(LedgerEntry.transaction_id == transaction_id))
    assert count == expected, f"transaction {transaction_id} has {count} ledger entries, expected {expected}"
