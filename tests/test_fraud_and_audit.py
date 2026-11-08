import uuid
from decimal import Decimal


def idem() -> str:
    return str(uuid.uuid4())


def make_wallet(client, headers, currency="ILS"):
    return client.post("/api/v1/wallets", json={"currency": currency}, headers=headers).json()


def balance(client, wallet_id: int, headers: dict) -> Decimal:
    return Decimal(client.get(f"/api/v1/wallets/{wallet_id}", headers=headers).json()["balance"])


def test_fraud_rules_require_admin_to_create(client, auth):
    r = client.post("/api/v1/fraud/rules", json={"name": "x", "rule_type": "large_amount", "action": "block"}, headers=auth)
    assert r.status_code == 403


def test_large_amount_rule_blocks_transfer(client, auth, auth_bob, admin_auth):
    client.post(
        "/api/v1/fraud/rules",
        json={"name": "Large amount", "rule_type": "large_amount", "config": {"threshold": 500}, "action": "block"},
        headers=admin_auth,
    )
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 1000}, headers={**auth, "Idempotency-Key": idem()}
    )

    r = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 600},
        headers={**auth, "Idempotency-Key": idem()},
    )
    assert r.status_code == 422
    assert "fraud" in r.json()["detail"].lower()

    # Blocked transfer must not have moved any money.
    assert balance(client, sender["id"], auth) == Decimal("1000.00")
    assert balance(client, receiver["id"], auth_bob) == Decimal("0.00")

    events = client.get("/api/v1/fraud/events", headers=admin_auth).json()
    assert events["total"] == 1
    assert events["items"][0]["action"] == "block"


def test_review_rule_allows_transfer_but_logs_event(client, auth, auth_bob, admin_auth):
    client.post(
        "/api/v1/fraud/rules",
        json={"name": "Watch large", "rule_type": "large_amount", "config": {"threshold": 500}, "action": "review"},
        headers=admin_auth,
    )
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 1000}, headers={**auth, "Idempotency-Key": idem()}
    )

    r = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 600},
        headers={**auth, "Idempotency-Key": idem()},
    )
    assert r.status_code == 201, r.text
    assert balance(client, receiver["id"], auth_bob) == Decimal("600.00")

    events = client.get("/api/v1/fraud/events", headers=admin_auth).json()
    assert events["items"][0]["action"] == "review"


def test_deactivated_rule_no_longer_applies(client, auth, auth_bob, admin_auth):
    rule = client.post(
        "/api/v1/fraud/rules",
        json={"name": "Large", "rule_type": "large_amount", "config": {"threshold": 500}, "action": "block"},
        headers=admin_auth,
    ).json()
    client.post(f"/api/v1/fraud/rules/{rule['id']}/deactivate", headers=admin_auth)

    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 1000}, headers={**auth, "Idempotency-Key": idem()}
    )
    r = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 600},
        headers={**auth, "Idempotency-Key": idem()},
    )
    assert r.status_code == 201


def test_audit_log_requires_admin(client, auth):
    assert client.get("/api/v1/audit", headers=auth).status_code == 403


def test_audit_log_records_transfer(client, auth, auth_bob, admin_auth):
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()}
    )
    client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 10},
        headers={**auth, "Idempotency-Key": idem()},
    )

    r = client.get("/api/v1/audit", params={"action": "transaction.transfer"}, headers=admin_auth)
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_admin_stats_reflect_activity(client, auth, auth_bob, admin_auth):
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()}
    )
    client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 10},
        headers={**auth, "Idempotency-Key": idem()},
    )

    r = client.get("/api/v1/admin/stats", headers=admin_auth)
    assert r.status_code == 200
    body = r.json()
    assert body["transactions_by_status"]["completed"] == 2
    assert body["completed_transaction_volume"] == 110.0
