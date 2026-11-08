from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.payment_request import PaymentRequestCreate, PaymentRequestOut
from app.services import payment_request_service

router = APIRouter(prefix="/payment-requests", tags=["Payment Requests"])


@router.post("", response_model=PaymentRequestOut, status_code=201)
def create_payment_request(data: PaymentRequestCreate, db: DBSession, user: CurrentUser) -> PaymentRequestOut:
    pr = payment_request_service.create(db, user, data)
    return PaymentRequestOut.model_validate(pr)


@router.get("", response_model=list[PaymentRequestOut])
def list_payment_requests(db: DBSession, user: CurrentUser) -> list[PaymentRequestOut]:
    return [PaymentRequestOut.model_validate(pr) for pr in payment_request_service.list_mine(db, user)]


@router.post("/{request_id}/accept", response_model=PaymentRequestOut)
def accept_payment_request(request_id: int, db: DBSession, user: CurrentUser) -> PaymentRequestOut:
    pr = payment_request_service.accept(db, request_id, user)
    return PaymentRequestOut.model_validate(pr)


@router.post("/{request_id}/decline", response_model=PaymentRequestOut)
def decline_payment_request(request_id: int, db: DBSession, user: CurrentUser) -> PaymentRequestOut:
    pr = payment_request_service.decline(db, request_id, user)
    return PaymentRequestOut.model_validate(pr)


@router.post("/{request_id}/cancel", response_model=PaymentRequestOut)
def cancel_payment_request(request_id: int, db: DBSession, user: CurrentUser) -> PaymentRequestOut:
    pr = payment_request_service.cancel(db, request_id, user)
    return PaymentRequestOut.model_validate(pr)
