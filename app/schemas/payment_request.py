from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PaymentRequestStatus


class PaymentRequestCreate(BaseModel):
    requester_wallet_id: int
    payer_wallet_id: int
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    description: str | None = None


class PaymentRequestOut(BaseModel):
    id: int
    requester_wallet_id: int
    payer_wallet_id: int
    amount: Decimal
    currency: str
    status: PaymentRequestStatus
    description: str | None
    transaction_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
