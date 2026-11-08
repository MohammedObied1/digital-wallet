import uuid
from decimal import Decimal

from tests.conftest import TestingSession
from tests.ledger_assertions import (
    assert_internal_transfers_balanced,
    assert_no_orphan_ledger_entries,
    assert_transaction_ledger_entry_count,
    assert_wallet_matches_ledger,
)


def idem() -> str:
    return str(uuid.uuid4())


def make_wallet(client, headers, currency="ILS"):
    return client.post("/api/v1/wallets", json={"currency": currency}, headers=headers).json()


def balance(client, wallet_id: int, headers: dict) -> Decimal:
    return Decimal(client.get(f"/api/v1/wallets/{wallet_id}", headers=headers).json()["balance"])


def test_ledger_rebuild_matches_cached_balance_after_mixed_activity(client, auth, auth_bob):
    a = make_wallet(client, auth)
    b = make_wallet(client, auth_bob)

    client.post("/api/v1/transactions/deposit", json={"wallet_id": a["id"], "amount": 200}, headers={**auth, "Idempotency-Key": idem()})
    client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": a["id"], "receiver_wallet_id": b["id"], "amount": 50},
        headers={**auth, "Idempotency-Key": idem()},
    )
    client.post("/api/v1/transactions/withdraw", json={"wallet_id": b["id"], "amount": 20}, headers={**auth_bob, "Idempotency-Key": idem()})
    txn = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": a["id"], "receiver_wallet_id": b["id"], "amount": 10},
        headers={**auth, "Idempotency-Key": idem()},
    ).json()
    client.post(f"/api/v1/transactions/{txn['id']}/refund", json={}, headers={**auth_bob, "Idempotency-Key": idem()})

    cached_a = balance(client, a["id"], auth)
    cached_b = balance(client, b["id"], auth_bob)

    db = TestingSession()
    try:
        assert assert_wallet_matches_ledger(db, a["id"]) == cached_a
        assert assert_wallet_matches_ledger(db, b["id"]) == cached_b
        assert_internal_transfers_balanced(db)
        assert_no_orphan_ledger_entries(db)
    finally:
        db.close()

    # Sanity: total money in the (closed) two-wallet system is conserved (deposit is the only
    # external inflow; the withdrawal is the only external outflow).
    assert cached_a + cached_b == Decimal("200.00") - Decimal("20.00")


def test_failed_transaction_leaves_no_ledger_entries_but_is_audited(client, auth):
    """A withdrawal that fails validation (insufficient funds) must not write any ledger rows —
    money never moved — but the failed *attempt* must still be recorded as a FAILED transaction
    with an audit log entry, per the "Transfer failure" audit event this project's design commits
    to (see transaction_service._fail_and_commit). Before that existed, a failure like this rolled
    back everything, including the Transaction row itself, leaving zero trace it ever happened.
    """
    w = make_wallet(client, auth)
    r = client.post("/api/v1/transactions/withdraw", json={"wallet_id": w["id"], "amount": 50}, headers={**auth, "Idempotency-Key": idem()})
    assert r.status_code == 422

    db = TestingSession()
    try:
        assert_internal_transfers_balanced(db)  # trivially true (zero entries), but must not error
        assert_no_orphan_ledger_entries(db)

        from app.models import AuditLog, Transaction, TransactionStatus

        failed = db.query(Transaction).filter(Transaction.status == TransactionStatus.FAILED).one()
        assert failed.type.value == "withdrawal"
        audit_entry = db.query(AuditLog).filter(AuditLog.action == "transaction.withdrawal.failed").one()
        assert audit_entry.entity_id == str(failed.id)
    finally:
        db.close()


def test_transfer_produces_exactly_two_ledger_entries(client, auth, auth_bob):
    """One debit (sender) + one credit (receiver) — never more, regardless of how many times an
    idempotent retry hits the endpoint.
    """
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()}
    )
    key = idem()
    body = {"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 40}
    first = client.post("/api/v1/transactions/transfer", json=body, headers={**auth, "Idempotency-Key": key}).json()
    # Retry with the same idempotency key — must replay, not create a second transfer.
    second = client.post("/api/v1/transactions/transfer", json=body, headers={**auth, "Idempotency-Key": key}).json()
    assert first["id"] == second["id"]

    db = TestingSession()
    try:
        assert_transaction_ledger_entry_count(db, first["id"], expected=2)
        assert_internal_transfers_balanced(db)
    finally:
        db.close()

    assert balance(client, sender["id"], auth) == Decimal("60.00")  # not 20 — the retry didn't re-apply


def test_reversed_transaction_preserves_ledger_balance(client, auth, auth_bob, admin_auth):
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()}
    )
    txn = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 40},
        headers={**auth, "Idempotency-Key": idem()},
    ).json()
    client.post(f"/api/v1/transactions/{txn['id']}/reverse", headers={**admin_auth, "Idempotency-Key": idem()})

    db = TestingSession()
    try:
        assert_wallet_matches_ledger(db, sender["id"])
        assert_wallet_matches_ledger(db, receiver["id"])
        assert_internal_transfers_balanced(db)
    finally:
        db.close()

    # The transfer (2 entries) + the reversal (2 entries) = 4 total, never re-applied.
    assert balance(client, sender["id"], auth) == Decimal("100.00")
    assert balance(client, receiver["id"], auth_bob) == Decimal("0.00")
