import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal


def idem() -> str:
    return str(uuid.uuid4())


def make_wallet(client, headers, currency="ILS"):
    return client.post("/api/v1/wallets", json={"currency": currency}, headers=headers).json()


def balance(client, wallet_id: int, headers: dict) -> Decimal:
    return Decimal(client.get(f"/api/v1/wallets/{wallet_id}", headers=headers).json()["balance"])


def deposit(client, wallet_id: int, amount, headers: dict) -> None:
    client.post(
        "/api/v1/transactions/deposit",
        json={"wallet_id": wallet_id, "amount": amount},
        headers={**headers, "Idempotency-Key": idem()},
    )


def test_create_and_accept_payment_request(client, auth, auth_bob):
    requester = make_wallet(client, auth)  # alice requests money
    payer = make_wallet(client, auth_bob)  # bob will pay
    deposit(client, payer["id"], 100, auth_bob)

    pr = client.post(
        "/api/v1/payment-requests",
        json={"requester_wallet_id": requester["id"], "payer_wallet_id": payer["id"], "amount": 30},
        headers=auth,
    )
    assert pr.status_code == 201, pr.text
    pr_id = pr.json()["id"]

    r = client.post(f"/api/v1/payment-requests/{pr_id}/accept", headers=auth_bob)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"
    assert r.json()["transaction_id"] is not None

    assert balance(client, requester["id"], auth) == Decimal("30.00")
    assert balance(client, payer["id"], auth_bob) == Decimal("70.00")


def test_decline_payment_request_moves_no_money(client, auth, auth_bob):
    requester = make_wallet(client, auth)
    payer = make_wallet(client, auth_bob)
    deposit(client, payer["id"], 100, auth_bob)

    pr = client.post(
        "/api/v1/payment-requests",
        json={"requester_wallet_id": requester["id"], "payer_wallet_id": payer["id"], "amount": 30},
        headers=auth,
    ).json()

    r = client.post(f"/api/v1/payment-requests/{pr['id']}/decline", headers=auth_bob)
    assert r.status_code == 200
    assert r.json()["status"] == "declined"
    assert balance(client, payer["id"], auth_bob) == Decimal("100.00")


def test_only_payer_can_accept(client, auth, auth_bob):
    requester = make_wallet(client, auth)
    payer = make_wallet(client, auth_bob)
    pr = client.post(
        "/api/v1/payment-requests",
        json={"requester_wallet_id": requester["id"], "payer_wallet_id": payer["id"], "amount": 30},
        headers=auth,
    ).json()

    r = client.post(f"/api/v1/payment-requests/{pr['id']}/accept", headers=auth)
    assert r.status_code == 404


def test_cannot_accept_twice(client, auth, auth_bob):
    requester = make_wallet(client, auth)
    payer = make_wallet(client, auth_bob)
    deposit(client, payer["id"], 100, auth_bob)
    pr = client.post(
        "/api/v1/payment-requests",
        json={"requester_wallet_id": requester["id"], "payer_wallet_id": payer["id"], "amount": 30},
        headers=auth,
    ).json()

    assert client.post(f"/api/v1/payment-requests/{pr['id']}/accept", headers=auth_bob).status_code == 200
    r = client.post(f"/api/v1/payment-requests/{pr['id']}/accept", headers=auth_bob)
    assert r.status_code == 409


def test_concurrent_accept_only_pays_once(client, auth, auth_bob):
    """Two racing accept() calls for the same payment request must not both transfer money — see
    payment_request_service._get_pending_for_payer's `for_update=True` path and
    ledger_service.wallet_lock, which together close this race for both single-process (the
    in-process lock) and multi-process (the row lock) deployments.
    """
    requester = make_wallet(client, auth)
    payer = make_wallet(client, auth_bob)
    deposit(client, payer["id"], 100, auth_bob)
    pr = client.post(
        "/api/v1/payment-requests",
        json={"requester_wallet_id": requester["id"], "payer_wallet_id": payer["id"], "amount": 30},
        headers=auth,
    ).json()

    def accept(_: int):
        return client.post(f"/api/v1/payment-requests/{pr['id']}/accept", headers=auth_bob)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], f"expected exactly one accept and one conflict, got {statuses}"
    assert balance(client, payer["id"], auth_bob) == Decimal("70.00")
    assert balance(client, requester["id"], auth) == Decimal("30.00")


def test_list_mine_shows_both_sides(client, auth, auth_bob):
    requester = make_wallet(client, auth)
    payer = make_wallet(client, auth_bob)
    client.post(
        "/api/v1/payment-requests",
        json={"requester_wallet_id": requester["id"], "payer_wallet_id": payer["id"], "amount": 30},
        headers=auth,
    )

    assert len(client.get("/api/v1/payment-requests", headers=auth).json()) == 1
    assert len(client.get("/api/v1/payment-requests", headers=auth_bob).json()) == 1
