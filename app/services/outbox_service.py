"""Transactional outbox: enqueue() must be called with the SAME db session that will commit the
financial change, so the event row and the ledger write land in one transaction. A separate
worker (workers/outbox_worker.py) polls for pending rows and dispatches them — notifications are
never sent from inside the financial transaction itself.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models import OutboxEvent


def enqueue(db: Session, event_type: str, payload: dict[str, Any]) -> OutboxEvent:
    event = OutboxEvent(event_type=event_type, payload=payload)
    db.add(event)
    return event
