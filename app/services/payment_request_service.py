from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import PaymentRequest, PaymentRequestStatus, User, Wallet
from app.schemas.payment_request import PaymentRequestCreate
from app.services import audit_service, ledger_service, transaction_service, wallet_service


def create(db: Session, requester: User, data: PaymentRequestCreate) -> PaymentRequest:
    requester_wallet = wallet_service.get_wallet_for_owner(db, data.requester_wallet_id, requester)
    payer_wallet = wallet_service.get_wallet_by_id(db, data.payer_wallet_id)

    pr = PaymentRequest(
        requester_wallet_id=requester_wallet.id,
        payer_wallet_id=payer_wallet.id,
        amount=data.amount,
        currency=requester_wallet.currency.value,
        description=data.description,
    )
    db.add(pr)
    db.flush()
    audit_service.record(db, action="payment_request.create", entity_type="payment_request", entity_id=pr.id, actor_user_id=requester.id)
    db.commit()
    db.refresh(pr)
    return pr


def _get_pending_for_payer(db: Session, request_id: int, payer: User, *, for_update: bool = False) -> PaymentRequest:
    # populate_existing=True: the caller (accept()) already loaded this row once before taking
    # the wallet lock, so without this we'd get the identity map's stale copy back — see
    # ledger_service.lock_wallets, which hit the identical bug for wallets.
    if for_update:
        # FOR UPDATE closes the same cross-process double-accept race that lock_transaction closes
        # for refund/reverse: without it, two concurrent accept() calls could both observe PENDING
        # before either commits and both execute the transfer. wallet_lock (in-process) already
        # prevents this within a single worker; this is what makes it safe across worker processes
        # too, under real PostgreSQL.
        stmt = select(PaymentRequest).where(PaymentRequest.id == request_id).with_for_update().execution_options(populate_existing=True)
        pr = db.scalar(stmt)
    else:
        pr = db.get(PaymentRequest, request_id, populate_existing=True)
    if not pr:
        raise NotFoundError("Payment request not found")
    if pr.payer_wallet.user_id != payer.id:
        raise NotFoundError("Payment request not found")
    if pr.status != PaymentRequestStatus.PENDING:
        raise ConflictError(f"Payment request is already {pr.status.value}")
    return pr


def accept(db: Session, request_id: int, payer: User) -> PaymentRequest:
    # payer_wallet_id / requester_wallet_id are immutable once a request is created, so it's safe
    # to read them without a lock just to know which wallets to lock.
    preview = db.get(PaymentRequest, request_id)
    if not preview:
        raise NotFoundError("Payment request not found")

    # Held for the whole read-check-transfer-commit below, not just the transfer, otherwise two
    # concurrent "accept" calls could both observe status=PENDING before either commits and both
    # transfer money — the same double-accept race the wallet-level lock exists to close for
    # transfers in general (see ledger_service's module docstring). Locking the actual wallet ids
    # (not the request id) also protects against this racing with an unrelated direct transfer/
    # withdrawal hitting the same wallets at the same time.
    with ledger_service.wallet_lock([preview.payer_wallet_id, preview.requester_wallet_id]):
        db.commit()  # end any transaction already open on `db` so the read below is fresh — see ledger_service docstring
        pr = _get_pending_for_payer(db, request_id, payer, for_update=True)
        txn = transaction_service.transfer(
            db, pr.payer_wallet, pr.requester_wallet, pr.amount, pr.description or f"Payment request #{pr.id}", payer
        )
        pr.status = PaymentRequestStatus.ACCEPTED
        pr.transaction_id = txn.id
        audit_service.record(db, action="payment_request.accept", entity_type="payment_request", entity_id=pr.id, actor_user_id=payer.id)
        db.commit()
        db.refresh(pr)
        return pr


def decline(db: Session, request_id: int, payer: User) -> PaymentRequest:
    pr = _get_pending_for_payer(db, request_id, payer)
    pr.status = PaymentRequestStatus.DECLINED
    audit_service.record(db, action="payment_request.decline", entity_type="payment_request", entity_id=pr.id, actor_user_id=payer.id)
    db.commit()
    db.refresh(pr)
    return pr


def cancel(db: Session, request_id: int, requester: User) -> PaymentRequest:
    pr = db.get(PaymentRequest, request_id)
    if not pr:
        raise NotFoundError("Payment request not found")
    if pr.requester_wallet.user_id != requester.id:
        raise NotFoundError("Payment request not found")
    if pr.status != PaymentRequestStatus.PENDING:
        raise ConflictError(f"Payment request is already {pr.status.value}")
    pr.status = PaymentRequestStatus.CANCELLED
    audit_service.record(db, action="payment_request.cancel", entity_type="payment_request", entity_id=pr.id, actor_user_id=requester.id)
    db.commit()
    db.refresh(pr)
    return pr


def list_mine(db: Session, user: User) -> list[PaymentRequest]:
    my_wallet_ids = select(Wallet.id).where(Wallet.user_id == user.id)
    stmt = (
        select(PaymentRequest)
        .where(or_(PaymentRequest.requester_wallet_id.in_(my_wallet_ids), PaymentRequest.payer_wallet_id.in_(my_wallet_ids)))
        .order_by(PaymentRequest.id.desc())
    )
    return list(db.scalars(stmt))
