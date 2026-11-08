from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import FraudAction


class FraudRuleCreate(BaseModel):
    name: str
    rule_type: str
    config: dict[str, Any] = {}
    action: FraudAction
    is_active: bool = True


class FraudRuleOut(BaseModel):
    id: int
    name: str
    rule_type: str
    config: dict[str, Any]
    action: FraudAction
    is_active: bool

    model_config = {"from_attributes": True}


class FraudEventOut(BaseModel):
    id: int
    transaction_id: int
    rule_id: int | None
    risk_score: float
    action: FraudAction
    details: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
