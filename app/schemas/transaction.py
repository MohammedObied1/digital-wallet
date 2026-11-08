from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import TransactionStatus, TransactionType

# Money is always a Decimal quantized to 2 places — never a binary float. A value with more than
# 2 decimal places is rejected outright (not silently rounded); see ARCHITECTURE.md's "Money
# representation" section for the full rationale.
Money = Decimal


class DepositRequest(BaseModel):
    wallet_id: int
    amount: Money = Field(gt=0, max_digits=18, decimal_places=2)
    description: str | None = None


class WithdrawRequest(BaseModel):
    wallet_id: int
    amount: Money = Field(gt=0, max_digits=18, decimal_places=2)
    description: str | None = None


class TransferRequest(BaseModel):
    sender_wallet_id: int
    receiver_wallet_id: int
    amount: Money = Field(gt=0, max_digits=18, decimal_places=2)
    description: str | None = None


class RefundRequest(BaseModel):
    amount: Money | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)


class TransactionOut(BaseModel):
    id: int
    type: TransactionType
    status: TransactionStatus
    sender_wallet_id: int | None
    receiver_wallet_id: int | None
    amount: Money
    currency: str
    description: str | None
    related_transaction_id: int | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
