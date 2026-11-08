"""Polls `outbox_events` for pending rows and dispatches them. This is intentionally simple: no
retry/backoff or dead-letter handling here — that machinery belongs to Project 2 (Distributed
Notification Platform), which this outbox is designed to eventually hand events off to. For now,
`dispatch` just logs the event; swap it for an HTTP call to the notification platform (or a
direct provider call) when that integration exists.

Run standalone: `python -m workers.outbox_worker`
Or import `drain_once(db)` from a test / another process for a single poll pass.
"""

import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import OutboxEvent, OutboxStatus

logger = logging.getLogger("wallet.outbox")


def dispatch(event: OutboxEvent) -> None:
    logger.info("outbox: dispatching %s #%s payload=%s", event.event_type, event.id, event.payload)


def drain_once(db: Session) -> int:
    """Process every currently-pending event once. Returns how many were published.

    `docker-compose.yml` runs exactly one `worker` replica, so a single process is the only
    consumer today — but `with_for_update(skip_locked=True)` is here so that changes if the queue
    ever needs to scale horizontally. Without it, two worker processes polling at the same moment
    would both select the same pending rows and both dispatch them (a duplicate notification is
    low-stakes here, but the pattern matters more once outbox events feed something less forgiving,
    like Project 2's notification platform). `skip_locked` means a second worker doesn't block
    behind the first's lock — it simply skips those rows and picks up whatever's left, so multiple
    replicas partition the queue instead of serializing on it. On SQLite (tests, and the `FOR
    UPDATE`-less dialect), this degrades to a plain SELECT — safe there anyway because SQLite tests
    only ever run this from one thread.
    """
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.status == OutboxStatus.PENDING)
        .order_by(OutboxEvent.id)
        .with_for_update(skip_locked=True)
    )
    pending = db.scalars(stmt).all()
    published = 0
    for event in pending:
        event.attempts += 1
        try:
            dispatch(event)
        except Exception:  # noqa: BLE001 - a bad event must not stop the batch
            logger.exception("outbox: dispatch failed for event #%s", event.id)
            if event.attempts >= settings.OUTBOX_MAX_ATTEMPTS:
                event.status = OutboxStatus.FAILED
            db.commit()
            continue
        else:
            event.status = OutboxStatus.PUBLISHED
            event.published_at = datetime.now(UTC)
            published += 1
            db.commit()
    return published


def run_forever() -> None:
    logger.info("outbox worker starting, poll interval=%ss", settings.OUTBOX_POLL_INTERVAL_SECONDS)
    while True:
        db = SessionLocal()
        try:
            drain_once(db)
        finally:
            db.close()
        time.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
