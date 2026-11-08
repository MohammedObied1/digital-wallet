"""The double-entry ledger engine. Every wallet balance change in the system must go through
`apply_entries` so that `ledger_entries` (the source of truth) and `wallets.balance` (the cache)
never drift apart.

Concurrency has two layers, both ordered ascending-by-wallet-id so two operations touching the
same pair of wallets in opposite directions can never deadlock each other:

  1. `wallet_lock` — an in-process threading.Lock per wallet id. This is what actually protects
     correctness on SQLite (whose dialect silently ignores `FOR UPDATE` — confirmed by a
     concurrency test that double-spent a wallet before this existed) and adds a cheap extra
     guard even under Postgres within a single process.
  2. `lock_wallets` — SELECT ... FOR UPDATE, which is what protects correctness across multiple
     processes/replicas talking to the same PostgreSQL database in production. A no-op on SQLite.

Callers must hold `wallet_lock` for the *entire* operation, including the final commit — releasing
it before commit would reopen the same race it's meant to close. See api/v1/transactions.py's
`_idempotent` wrapper, which acquires it around read-modify-write-commit as a whole.
"""

import threading
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientFundsError, NotFoundError, WalletNotActiveError
from app.models import LedgerEntry, LedgerEntryType, Transaction, Wallet, WalletStatus

_registry_lock = threading.Lock()
_wallet_locks: dict[int, threading.Lock] = {}


def _get_lock(wallet_id: int) -> threading.Lock:
    with _registry_lock:
        return _wallet_locks.setdefault(wallet_id, threading.Lock())


@contextmanager
def wallet_lock(wallet_ids: Iterable[int]):
    """Acquire the in-process locks for every wallet id, in a fixed ascending order, for the
    duration of the `with` block. Reentrant-safe across requests, not across threads.
    """
    ordered_ids = sorted({wid for wid in wallet_ids if wid is not None})
    acquired: list[threading.Lock] = []
    try:
        for wallet_id in ordered_ids:
            lock = _get_lock(wallet_id)
            lock.acquire()
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            lock.release()


@dataclass
class LedgerLine:
    wallet_id: int
    entry_type: LedgerEntryType
    amount: Decimal


def lock_wallets(db: Session, wallet_ids: Iterable[int]) -> dict[int, Wallet]:
    """Lock the given wallets for update, in a fixed (ascending id) order, and return them keyed
    by id. Raises NotFoundError if any wallet doesn't exist. Callers must already hold
    `wallet_lock` for the same ids — see module docstring.
    """
    ordered_ids = sorted(set(wallet_ids))
    # populate_existing=True is essential here: our sessions use expire_on_commit=False, so
    # without it SQLAlchemy's identity map would hand back whatever Wallet object was already
    # loaded earlier in this request (e.g. by wallet_service.get_wallet_for_owner) with its now-
    # stale attributes, silently ignoring the fresh row this FOR UPDATE query just fetched.
    stmt = select(Wallet).where(Wallet.id.in_(ordered_ids)).order_by(Wallet.id).with_for_update().execution_options(populate_existing=True)
    wallets = {w.id: w for w in db.scalars(stmt)}
    missing = set(ordered_ids) - wallets.keys()
    if missing:
        raise NotFoundError(f"Wallet(s) not found: {sorted(missing)}")
    return wallets


def lock_transaction(db: Session, transaction_id: int) -> Transaction:
    """Lock a single Transaction row for update and return a freshly-populated instance.

    Refund and reversal both start from a Transaction object fetched by the router *before* the
    in-process `wallet_lock` is acquired (see api/v1/transactions.py). Under a single process
    that in-memory object is a harmless snapshot, but across multiple worker processes two
    concurrent refund/reverse calls for the same transaction could both observe `status ==
    COMPLETED` before either commits, and both apply — a double refund/reversal. Re-fetching here,
    under `FOR UPDATE` and *after* the wallet lock is held, closes that race the same way
    `lock_wallets` closes it for balances: the second caller blocks until the first commits, then
    sees the now-REFUNDED/REVERSED status and can reject cleanly.
    """
    stmt = select(Transaction).where(Transaction.id == transaction_id).with_for_update().execution_options(populate_existing=True)
    txn = db.scalar(stmt)
    if txn is None:
        raise NotFoundError("Transaction not found")
    return txn


def require_active(wallet: Wallet) -> None:
    if wallet.status != WalletStatus.ACTIVE:
        raise WalletNotActiveError(f"Wallet {wallet.id} is {wallet.status.value}, not active")


def apply_entries(db: Session, transaction: Transaction, wallets: dict[int, Wallet], lines: list[LedgerLine]) -> None:
    """Write ledger entries for `lines` against already-locked `wallets`, updating each wallet's
    cached balance. Debits decrease a wallet's balance, credits increase it. Raises
    InsufficientFundsError if a debit would take a wallet negative.

    Callers must have locked every wallet in `lines` via `lock_wallets` first, within the same
    transaction, before calling this.
    """
    for line in lines:
        wallet = wallets[line.wallet_id]
        if line.entry_type == LedgerEntryType.DEBIT:
            if wallet.balance - line.amount < 0:
                raise InsufficientFundsError(f"Wallet {wallet.id} has insufficient funds")
            wallet.balance -= line.amount
        else:
            wallet.balance += line.amount
        wallet.available_balance = wallet.balance
        wallet.version += 1

        db.add(
            LedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=line.entry_type,
                amount=line.amount,
                currency=transaction.currency,
                balance_after=wallet.balance,
            )
        )


def rebuild_balance(db: Session, wallet_id: int) -> Decimal:
    """Recompute a wallet's balance purely from its ledger entries. Used by integrity tests and
    admin tooling to prove the cached `wallets.balance` column hasn't drifted from the ledger.
    """
    entries = db.scalars(select(LedgerEntry).where(LedgerEntry.wallet_id == wallet_id).order_by(LedgerEntry.id))
    balance = Decimal("0")
    for entry in entries:
        balance += entry.amount if entry.entry_type == LedgerEntryType.CREDIT else -entry.amount
    return balance
