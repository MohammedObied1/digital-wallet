from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: int | None
    action: str
    entity_type: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
