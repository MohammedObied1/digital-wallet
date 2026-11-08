import uuid
from decimal import Decimal


def idem() -> str:
    return str(uuid.uuid4())


def make_wallet(client, headers, currency="ILS"):
    r = client.post("/api/v1/wallets", json={"currency": currency}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def balance(client, wallet_id: int, headers: dict) -> Decimal:
    """Money is serialized as a Decimal string on the wire (see ARCHITECTURE.md's "Money
    representation" section) — parse it back to Decimal rather than comparing against a float.
    """
    return Decimal(client.get(f"/api/v1/wallets/{wallet_id}", headers=headers).json()["balance"])


def test_deposit_increases_balance(client, auth):
    w = make_wallet(client, auth)
    r = client.post(
        "/api/v1/transactions/deposit",
        json={"wallet_id": w["id"], "amount": 100},
        headers={**auth, "Idempotency-Key": idem()},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["type"] == "deposit"

    assert balance(client, w["id"], auth) == Decimal("100.00")


def test_deposit_is_idempotent(client, auth):
    w = make_wallet(client, auth)
    key = idem()
    r1 = client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 50}, headers={**auth, "Idempotency-Key": key})
    r2 = client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 50}, headers={**auth, "Idempotency-Key": key})
    assert r1.json()["id"] == r2.json()["id"]

    assert balance(client, w["id"], auth) == Decimal("50.00")  # not 100 — the second request replayed, didn't re-execute


def test_idempotency_key_is_scoped_per_user(client, auth, auth_bob):
    """Two different users reusing the exact same Idempotency-Key string on the same endpoint must
    not collide — each user's key space is their own. Regression test for the pre-fix behavior
    where IdempotencyRecord was keyed only by (idempotency_key, endpoint): user B picking the same
    key as user A would previously either get a spurious 409 conflict or, worse, user A's cached
    response body if the two requests happened to hash the same.
    """
    w_alice = make_wallet(client, auth)
    w_bob = make_wallet(client, auth_bob)
    shared_key = "shared-key-both-users-happen-to-pick"

    r_alice = client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": w_alice["id"], "amount": 50}, headers={**auth, "Idempotency-Key": shared_key}
    )
    r_bob = client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": w_bob["id"], "amount": 50}, headers={**auth_bob, "Idempotency-Key": shared_key}
    )

    assert r_alice.status_code == 201, r_alice.text
    assert r_bob.status_code == 201, r_bob.text
    assert r_alice.json()["id"] != r_bob.json()["id"]  # two distinct transactions, not one replayed for both
    assert balance(client, w_alice["id"], auth) == Decimal("50.00")
    assert balance(client, w_bob["id"], auth_bob) == Decimal("50.00")


def test_idempotency_key_reused_with_different_body_conflicts(client, auth):
    w = make_wallet(client, auth)
    key = idem()
    client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 50}, headers={**auth, "Idempotency-Key": key})
    r = client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 999}, headers={**auth, "Idempotency-Key": key})
    assert r.status_code == 409


def test_withdraw_insufficient_funds(client, auth):
    w = make_wallet(client, auth)
    r = client.post("/api/v1/transactions/withdraw", json={"wallet_id": w["id"], "amount": 10}, headers={**auth, "Idempotency-Key": idem()})
    assert r.status_code == 422


def test_withdraw_success(client, auth):
    w = make_wallet(client, auth)
    client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()})
    r = client.post("/api/v1/transactions/withdraw", json={"wallet_id": w["id"], "amount": 40}, headers={**auth, "Idempotency-Key": idem()})
    assert r.status_code == 201
    assert balance(client, w["id"], auth) == Decimal("60.00")


def test_transfer_moves_funds_between_wallets(client, auth, auth_bob):
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()}
    )

    r = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 30},
        headers={**auth, "Idempotency-Key": idem()},
    )
    assert r.status_code == 201, r.text

    assert balance(client, sender["id"], auth) == Decimal("70.00")
    assert balance(client, receiver["id"], auth_bob) == Decimal("30.00")


def test_transfer_insufficient_funds_leaves_both_balances_unchanged(client, auth, auth_bob):
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)

    r = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 30},
        headers={**auth, "Idempotency-Key": idem()},
    )
    assert r.status_code == 422

    assert balance(client, sender["id"], auth) == Decimal("0.00")
    assert balance(client, receiver["id"], auth_bob) == Decimal("0.00")


def test_cannot_transfer_from_someone_elses_wallet(client, auth, auth_bob):
    bob_wallet = make_wallet(client, auth_bob)
    alice_wallet = make_wallet(client, auth)
    r = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": bob_wallet["id"], "receiver_wallet_id": alice_wallet["id"], "amount": 10},
        headers={**auth, "Idempotency-Key": idem()},
    )
    assert r.status_code == 404


def test_transfer_respects_max_transaction_amount(client, auth, auth_bob):
    sender = make_wallet(client, auth)
    receiver = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/transactions/deposit", json={"wallet_id": sender["id"], "amount": 50_000}, headers={**auth, "Idempotency-Key": idem()}
    )

    r = client.post(
        "/api/v1/transactions/transfer",
        json={"sender_wallet_id": sender["id"], "receiver_wallet_id": receiver["id"], "amount": 20_000},
        headers={**auth, "Idempotency-Key": idem()},
    )
    assert r.status_code == 422
    assert "limit" in r.json()["detail"].lower()


def test_frozen_wallet_cannot_send_or_receive(client, auth, admin_auth):
    w = make_wallet(client, auth)
    client.post("/api/v1/transactions/deposit", json={"wallet_id": w["id"], "amount": 100}, headers={**auth, "Idempotency-Key": idem()})
    client.post(f"/api/v1/wallets/{w['id']}/freeze", headers=admin_auth)

    r = client.post("/api/v1/transactions/withdraw", json={"wallet_id": w["id"], "amount": 10}, headers={**auth, "Idempotency-Key": idem()})
    assert r.status_code == 422


def test_full_refund_reverts_transfer_and_marks_original_refunded(client, auth, auth_bob):
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

    r = client.post(f"/api/v1/transactions/{txn['id']}/refund", json={}, headers={**auth_bob, "Idempotency-Key": idem()})
    assert r.status_code == 201, r.text

    assert balance(client, sender["id"], auth) == Decimal("100.00")
    assert balance(client, receiver["id"], auth_bob) == Decimal("0.00")
    original = client.get(f"/api/v1/transactions/{txn['id']}", headers=auth).json()
    assert original["status"] == "refunded"


def test_reverse_requires_staff(client, auth, auth_bob):
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

    r = client.post(f"/api/v1/transactions/{txn['id']}/reverse", headers={**auth, "Idempotency-Key": idem()})
    assert r.status_code == 403


def test_admin_can_reverse_a_completed_transfer(client, auth, auth_bob, admin_auth):
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

    r = client.post(f"/api/v1/transactions/{txn['id']}/reverse", headers={**admin_auth, "Idempotency-Key": idem()})
    assert r.status_code == 201, r.text

    assert balance(client, sender["id"], auth) == Decimal("100.00")
    assert balance(client, receiver["id"], auth_bob) == Decimal("0.00")


def test_transaction_history_scoped_to_own_wallets(client, auth, auth_bob):
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

    mine = client.get("/api/v1/transactions", headers=auth).json()
    assert mine["total"] == 2  # my deposit + my transfer

    bobs = client.get("/api/v1/transactions", headers=auth_bob).json()
    assert bobs["total"] == 1  # only the transfer touches bob's wallet
