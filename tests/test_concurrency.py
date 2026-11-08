"""Concurrency tests.

Caveat (documented in ARCHITECTURE.md too): this test suite runs against the in-memory SQLite
StaticPool used by the rest of the test suite, which is a single shared connection — so two
"concurrent" requests here are serialized by that one connection regardless of our own
SELECT ... FOR UPDATE logic. This test proves the *outcome* we require (no double-spend, exactly
one of two racing withdrawals succeeds) but does not, by itself, prove that our row-locking
strategy specifically is what enforces it under real concurrent connections. A definitive test
needs PostgreSQL with a real connection pool (see docker-compose's `db` service) — that's called
out as follow-up work, since this sandboxed environment has no Docker to run Postgres in.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from tests.conftest import TestingSession
from tests.ledger_assertions import assert_internal_transfers_balanced, assert_wallet_matches_ledger


def idem() -> str:
    return str(uuid.uuid4())


def balance(client, wallet_id: int, headers: dict) -> Decimal:
    return Decimal(client.get(f"/api/v1/wallets/{wallet_id}", headers=headers).json()["balance"])


def test_two_concurrent_withdrawals_only_one_succeeds(client, auth):
    w = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()})

    # Reuse the single `client` fixture (its app lifespan already started) rather than spinning
    # up a second TestClient per thread — two lifespans racing to run DDL on the same shared
    # SQLite connection crashed the interpreter (access violation) before this fix.
    def withdraw(_: int):
        return client.post(
            "/api/v1/transactions/withdraw",
            json={"wallet_id": w["id"], "amount": 80},
            headers={**auth, "Idempotency-Key": idem()},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(withdraw, range(2)))

    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 422], f"expected exactly one success and one insufficient-funds rejection, got {statuses}"

    assert balance(client, w["id"], auth) == Decimal("20.00")  # 100 - 80, never negative, never double-applied

    db = TestingSession()
    try:
        assert_wallet_matches_ledger(db, w["id"])
        assert_internal_transfers_balanced(db)
    finally:
        db.close()


def test_two_concurrent_transfers_only_one_succeeds(client, auth, auth_bob):
    """Same double-spend scenario as above, but for transfer (the endpoint that locks two wallets,
    not one) rather than withdrawal.
    """
    sender = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    receiver = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth_bob).json()
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()}
    )

    def transfer(_: int):
        return client.post(
            "/api/v1/transactions/transfer",
            json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 80},
            headers={**auth, "Idempotency-Key": idem()},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(transfer, range(2)))

    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 422], f"expected exactly one success and one insufficient-funds rejection, got {statuses}"
    assert balance(client, sender["id"], auth) == Decimal("20.00")
    assert balance(client, receiver["id"], auth_bob) == Decimal("80.00")

    db = TestingSession()
    try:
        assert_wallet_matches_ledger(db, sender["id"])
        assert_wallet_matches_ledger(db, receiver["id"])
        assert_internal_transfers_balanced(db)
    finally:
        db.close()


def test_two_concurrent_reversal_attempts_only_one_applies(client, auth, auth_bob, admin_auth):
    """Regression test for the race ledger_service.lock_transaction closes: two racing `reverse`
    calls for the same transaction must not both apply. Before that fix, `reverse()` checked
    `original.status` from an object fetched *before* the wallet lock was acquired, so a second
    caller could still see a stale `COMPLETED` status after the first reversal had already
    committed — a double reversal.
    """
    sender = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    receiver = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth_bob).json()
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()}
    )
    txn = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 40},
        headers={**auth, "Idempotency-Key": idem()},
    ).json()

    def reverse(_: int):
        return client.post(f"/api/v1/transactions/{txn['id']}/reverse", headers={**admin_auth, "Idempotency-Key": idem()})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reverse, range(2)))

    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 422], f"expected exactly one reversal to apply and one to be rejected, got {statuses}"

    # If the race weren't closed, the sender would end up with 140 (100 + two reversals of 40).
    assert balance(client, sender["id"], auth) == Decimal("100.00")
    assert balance(client, receiver["id"], auth_bob) == Decimal("0.00")

    db = TestingSession()
    try:
        assert_wallet_matches_ledger(db, sender["id"])
        assert_wallet_matches_ledger(db, receiver["id"])
        assert_internal_transfers_balanced(db)
    finally:
        db.close()
