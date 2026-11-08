"""Concurrency tests against a *real* PostgreSQL connection pool.

`test_concurrency.py` proves the right outcome (no double-spend) but runs against the shared
single-connection SQLite `StaticPool` the rest of the suite uses — so it can't distinguish "our
`SELECT ... FOR UPDATE` locking made this safe" from "there was only ever one connection, so
nothing could race in the first place." This file re-runs the same scenarios against Postgres with
a real multi-connection pool, so two "concurrent" requests are genuinely issued from two different
database connections at the same time.

Skipped unless `POSTGRES_TEST_DATABASE_URL` is set, because this sandboxed development environment
has no Docker/Postgres available to run these against locally. CI provides a `postgres:16-alpine`
service container and sets this variable — see `.github/workflows/ci.yml` — so these do run on
every push even though they can't be executed in this environment. Run locally with:

    docker run --rm -e POSTGRES_PASSWORD=wallet -e POSTGRES_USER=wallet -e POSTGRES_DB=wallet_test -p 5433:5432 postgres:16-alpine
    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg2://wallet:wallet@localhost:5433/wallet_test pytest tests/test_postgres_concurrency.py
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from tests.ledger_assertions import assert_internal_transfers_balanced, assert_wallet_matches_ledger

PG_URL = os.environ.get("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="set POSTGRES_TEST_DATABASE_URL to run real-Postgres concurrency tests")

if PG_URL:
    engine = create_engine(PG_URL, pool_size=10, max_overflow=10)
    PgSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override_get_db():
        db = PgSession()
        try:
            yield db
        finally:
            db.close()


def idem() -> str:
    return str(uuid.uuid4())


def balance(client, wallet_id: int, headers: dict) -> Decimal:
    return Decimal(client.get(f"/api/v1/wallets/{wallet_id}", headers=headers).json()["balance"])


@pytest.fixture
def pg_client():
    """A TestClient backed by a real multi-connection Postgres pool instead of the default
    single-connection SQLite override — restores whatever override (if any) was active before, so
    this file can coexist with the rest of the suite regardless of run order.
    """
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=engine)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        Base.metadata.drop_all(bind=engine)
        if previous is not None:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)


def register_and_login(client: TestClient, username: str) -> dict:
    client.post(
        "/api/v1/auth/register",
        json={"email": f"{username}@example.com", "username": username, "password": "Passw0rd123", "full_name": username.title()},
    )
    r = client.post("/api/v1/auth/login", data={"username": username, "password": "Passw0rd123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_double_spend_prevented_under_real_postgres_locking(pg_client):
    auth = register_and_login(pg_client, "pg_alice")
    w = pg_client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    pg_client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()})

    def withdraw(_: int):
        return pg_client.post(
            "/api/v1/transactions/withdraw", json={"wallet_id": w["id"], "amount": 80}, headers={**auth, "Idempotency-Key": idem()}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(withdraw, range(2)))

    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 422]
    assert balance(pg_client, w["id"], auth) == Decimal("20.00")

    db = PgSession()
    try:
        assert_wallet_matches_ledger(db, w["id"])
    finally:
        db.close()


def test_double_accept_prevented_under_real_postgres_locking(pg_client):
    alice = register_and_login(pg_client, "pg_bob_requester")
    bob = register_and_login(pg_client, "pg_bob_payer")
    requester = pg_client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=alice).json()
    payer = pg_client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=bob).json()
    pg_client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": payer["id"], "amount": 100}, headers={**bob, "Idempotency-Key": idem()}
    )
    pr = pg_client.post(
        "/api/v1/payment-requests",
        json={"requester_wallet_id": requester["id"], "payer_wallet_id": payer["id"], "amount": 30},
        headers=alice,
    ).json()

    def accept(_: int):
        return pg_client.post(f"/api/v1/payment-requests/{pr['id']}/accept", headers=bob)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409]
    assert balance(pg_client, payer["id"], bob) == Decimal("70.00")


def test_concurrent_reversals_prevented_under_real_postgres_locking(pg_client):
    admin_headers = register_and_login(pg_client, "pg_admin")
    # Promote via a direct DB write — there is no self-service "become admin" API, by design.
    from app.models import User, UserRole

    db = PgSession()
    try:
        me = pg_client.get("/api/v1/auth/me", headers=admin_headers).json()
        user = db.get(User, me["id"])
        user.role = UserRole.ADMIN
        db.commit()
    finally:
        db.close()

    sender_auth = register_and_login(pg_client, "pg_rev_sender")
    receiver_auth = register_and_login(pg_client, "pg_rev_receiver")
    sender = pg_client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=sender_auth).json()
    receiver = pg_client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=receiver_auth).json()
    pg_client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 100}, headers={**sender_auth, "Idempotency-Key": idem()}
    )
    txn = pg_client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 40},
        headers={**sender_auth, "Idempotency-Key": idem()},
    ).json()

    def reverse(_: int):
        return pg_client.post(f"/api/v1/transactions/{txn['id']}/reverse", headers={**admin_headers, "Idempotency-Key": idem()})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reverse, range(2)))

    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 422]
    assert balance(pg_client, sender["id"], sender_auth) == Decimal("100.00")

    db = PgSession()
    try:
        assert_internal_transfers_balanced(db)
    finally:
        db.close()
