from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DBSession, PageParams
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import Transaction, TransactionStatus, TransactionType, User, UserRole, Wallet
from app.schemas.transaction import DepositRequest, RefundRequest, TransactionOut, TransferRequest, WithdrawRequest
from app.services import idempotency_service, ledger_service, transaction_service, wallet_service

router = APIRouter(prefix="/transactions", tags=["Transactions"])

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key")]


def _idempotent(db: DBSession, user: User, endpoint: str, key: str, body: dict, wallet_ids: list[int], run):
    """Shared idempotency wrapper: replay a cached response for a repeated (user, key, endpoint,
    body); reject a repeated key used with a different body; otherwise run the operation and cache
    its result in the same DB transaction that commits the financial change.

    Idempotency records are scoped per-user (see IdempotencyRecord's docstring) — passing `user`
    here, not just the wallet ids, is what closes the cross-user idempotency-key collision.

    `wallet_ids` are locked in-process (ledger_service.wallet_lock) for the *entire* read-modify-
    write-commit below — not just inside the service call — because releasing the lock before
    commit would reopen the exact race it exists to close (see ledger_service's module docstring).
    """
    with ledger_service.wallet_lock(wallet_ids):
        # By this point `db`'s transaction may already have started (e.g. the auth dependency's
        # earlier SELECT) and, on SQLite, holds a snapshot from then — stale by the time we get
        # the lock. Ending it here (nothing has been written yet) means the reads below start a
        # fresh transaction that sees whatever the previous lock holder just committed. Harmless
        # on Postgres, where each statement already reads the latest committed data anyway.
        db.commit()
        request_hash = idempotency_service.hash_body(body)
        cached = idempotency_service.get_cached(db, user.id, key, endpoint, request_hash)
        if cached is not None:
            return JSONResponse(status_code=cached.status_code, content=cached.response_body)

        txn = run()
        response = TransactionOut.model_validate(txn).model_dump(mode="json")
        idempotency_service.store(db, user.id, key, endpoint, request_hash, 201, response)
        idempotency_service.commit_atomically(db)
        return JSONResponse(status_code=201, content=response)


def _is_party(db: DBSession, txn: Transaction, user: User) -> bool:
    wallet_ids = {w for w in (txn.sender_wallet_id, txn.receiver_wallet_id) if w is not None}
    if not wallet_ids:
        return False
    owned = db.scalar(select(func.count()).where(Wallet.id.in_(wallet_ids), Wallet.user_id == user.id))
    return bool(owned)


def _require_party_or_staff(db: DBSession, txn: Transaction, user: User) -> None:
    if user.role in (UserRole.SUPPORT, UserRole.ADMIN) or _is_party(db, txn, user):
        return
    raise NotFoundError("Transaction not found")


@router.post("/deposit")
def deposit(data: DepositRequest, db: DBSession, user: CurrentUser, idempotency_key: IdempotencyKey):
    wallet = wallet_service.get_wallet_for_owner(db, data.wallet_id, user)
    return _idempotent(
        db,
        user,
        "deposit",
        idempotency_key,
        data.model_dump(),
        [wallet.id],
        lambda: transaction_service.deposit(db, wallet, data.amount, data.description, user),
    )


@router.post("/withdraw")
def withdraw(data: WithdrawRequest, db: DBSession, user: CurrentUser, idempotency_key: IdempotencyKey):
    wallet = wallet_service.get_wallet_for_owner(db, data.wallet_id, user)
    return _idempotent(
        db,
        user,
        "withdraw",
        idempotency_key,
        data.model_dump(),
        [wallet.id],
        lambda: transaction_service.withdraw(db, wallet, data.amount, data.description, user),
    )


@router.post("/transfer")
def transfer(data: TransferRequest, db: DBSession, user: CurrentUser, idempotency_key: IdempotencyKey):
    sender = wallet_service.get_wallet_for_owner(db, data.sender_wallet_id, user)
    receiver = wallet_service.get_wallet_by_id(db, data.receiver_wallet_id)
    return _idempotent(
        db,
        user,
        "transfer",
        idempotency_key,
        data.model_dump(),
        [sender.id, receiver.id],
        lambda: transaction_service.transfer(db, sender, receiver, data.amount, data.description, user),
    )


@router.post("/{transaction_id}/refund")
def refund(transaction_id: int, data: RefundRequest, db: DBSession, user: CurrentUser, idempotency_key: IdempotencyKey):
    original = db.get(Transaction, transaction_id)
    if not original:
        raise NotFoundError("Transaction not found")
    _require_party_or_staff(db, original, user)
    wallet_ids = [w for w in (original.sender_wallet_id, original.receiver_wallet_id) if w is not None]
    return _idempotent(
        db,
        user,
        "refund",
        idempotency_key,
        {"transaction_id": transaction_id, **data.model_dump()},
        wallet_ids,
        lambda: transaction_service.refund(db, original, user, data.amount),
    )


@router.post("/{transaction_id}/reverse")
def reverse(transaction_id: int, db: DBSession, user: CurrentUser, idempotency_key: IdempotencyKey):
    if user.role not in (UserRole.SUPPORT, UserRole.ADMIN):
        raise ForbiddenError("Only support/admin can reverse a transaction")
    original = db.get(Transaction, transaction_id)
    if not original:
        raise NotFoundError("Transaction not found")
    wallet_ids = [w for w in (original.sender_wallet_id, original.receiver_wallet_id) if w is not None]
    return _idempotent(
        db,
        user,
        "reverse",
        idempotency_key,
        {"transaction_id": transaction_id},
        wallet_ids,
        lambda: transaction_service.reverse(db, original, user),
    )


@router.get("")
def list_transactions(
    db: DBSession,
    user: CurrentUser,
    page: PageParams,
    wallet_id: int | None = None,
    status: TransactionStatus | None = None,
    type: TransactionType | None = None,
):
    stmt = select(Transaction)
    if user.role not in (UserRole.SUPPORT, UserRole.ADMIN):
        my_wallet_ids = select(Wallet.id).where(Wallet.user_id == user.id)
        stmt = stmt.where(or_(Transaction.sender_wallet_id.in_(my_wallet_ids), Transaction.receiver_wallet_id.in_(my_wallet_ids)))

    if wallet_id is not None:
        stmt = stmt.where(or_(Transaction.sender_wallet_id == wallet_id, Transaction.receiver_wallet_id == wallet_id))
    if status is not None:
        stmt = stmt.where(Transaction.status == status)
    if type is not None:
        stmt = stmt.where(Transaction.type == type)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Transaction.id.desc()).offset(page.offset).limit(page.size)).all()
    return page.build([TransactionOut.model_validate(t) for t in rows], total)


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: int, db: DBSession, user: CurrentUser) -> TransactionOut:
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise NotFoundError("Transaction not found")
    _require_party_or_staff(db, txn, user)
    return TransactionOut.model_validate(txn)
