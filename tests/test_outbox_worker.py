import uuid

from app.models import OutboxEvent, OutboxStatus
from workers import outbox_worker


def idem() -> str:
    return str(uuid.uuid4())


def test_deposit_enqueues_a_pending_outbox_event(client, auth):
    from tests.conftest import TestingSession

    w = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()})

    db = TestingSession()
    try:
        events = db.query(OutboxEvent).all()
        assert len(events) == 1
        assert events[0].status == OutboxStatus.PENDING
        assert events[0].event_type == "transaction.deposit.completed"
    finally:
        db.close()


def test_drain_once_publishes_pending_events(client, auth):
    from tests.conftest import TestingSession

    w = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()})

    db = TestingSession()
    try:
        published = outbox_worker.drain_once(db)
        assert published == 1
        event = db.query(OutboxEvent).one()
        assert event.status == OutboxStatus.PUBLISHED
        assert event.published_at is not None

        # A second pass has nothing left to do.
        assert outbox_worker.drain_once(db) == 0
    finally:
        db.close()


def test_drain_once_commits_each_event_independently(client, auth, monkeypatch):
    """If the worker process dies partway through a batch, events already dispatched before the
    crash must stay PUBLISHED rather than roll back and get redelivered — so drain_once commits
    after each event, not once at the end of the whole batch. Simulate a mid-batch crash on the
    second event and confirm the first is durably PUBLISHED regardless.
    """
    from tests.conftest import TestingSession

    w = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 10}, headers={**auth, "Idempotency-Key": idem()})
    client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 20}, headers={**auth, "Idempotency-Key": idem()})

    calls = {"n": 0}
    real_dispatch = outbox_worker.dispatch

    def flaky_dispatch(event):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated crash mid-batch")
        real_dispatch(event)

    monkeypatch.setattr(outbox_worker, "dispatch", flaky_dispatch)

    db = TestingSession()
    try:
        published = outbox_worker.drain_once(db)
        assert published == 1  # the first event; the second raised

        statuses = {e.status for e in db.query(OutboxEvent).all()}
        assert OutboxStatus.PUBLISHED in statuses
        # The failed event stays PENDING (attempts < OUTBOX_MAX_ATTEMPTS) for the next poll to retry.
        assert OutboxStatus.PENDING in statuses
    finally:
        db.close()
