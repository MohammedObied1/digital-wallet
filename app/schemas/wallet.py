from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import Currency, WalletStatus


class WalletCreate(BaseModel):
    currency: Currency
    label: str | None = None


class WalletOut(BaseModel):
    id: int
    user_id: int
    currency: Currency
    status: WalletStatus
    balance: Decimal
    available_balance: Decimal
    label: str | None

    model_config = {"from_attributes": True}
