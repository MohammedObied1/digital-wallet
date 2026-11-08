def test_create_wallet(client, auth):
    r = client.post("/api/v1/wallets", json={"currency": "ILS", "label": "Main"}, headers=auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["currency"] == "ILS"
    assert body["status"] == "active"
    assert body["balance"] == "0.00"  # Decimal serializes as a string on the wire — see ARCHITECTURE.md


def test_cannot_create_duplicate_currency_wallet(client, auth):
    client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth)
    r = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth)
    assert r.status_code == 409


def test_can_create_wallets_in_different_currencies(client, auth):
    assert client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).status_code == 201
    assert client.post("/api/v1/wallets", json={"currency": "USD"}, headers=auth).status_code == 201


def test_list_my_wallets(client, auth):
    client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth)
    client.post("/api/v1/wallets", json={"currency": "USD"}, headers=auth)
    r = client.get("/api/v1/wallets", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_cannot_see_others_wallet(client, auth, auth_bob):
    w = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    r = client.get(f"/api/v1/wallets/{w['id']}", headers=auth_bob)
    assert r.status_code == 404


def test_freeze_requires_admin(client, auth):
    w = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()
    r = client.post(f"/api/v1/wallets/{w['id']}/freeze", headers=auth)
    assert r.status_code == 403


def test_admin_can_freeze_and_unfreeze(client, auth, admin_auth):
    w = client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth).json()

    r = client.post(f"/api/v1/wallets/{w['id']}/freeze", headers=admin_auth)
    assert r.status_code == 200
    assert r.json()["status"] == "frozen"

    r = client.post(f"/api/v1/wallets/{w['id']}/unfreeze", headers=admin_auth)
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_wallet_search_requires_staff(client, auth):
    r = client.get("/api/v1/wallets/search", headers=auth)
    assert r.status_code == 403


def test_admin_can_search_wallets_across_users(client, auth, auth_bob, admin_auth):
    client.post("/api/v1/wallets", json={"currency": "ILS"}, headers=auth)
    client.post("/api/v1/wallets", json={"currency": "USD"}, headers=auth_bob)

    r = client.get("/api/v1/wallets/search", headers=admin_auth)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 2

    r = client.get("/api/v1/wallets/search?currency=USD", headers=admin_auth)
    assert r.status_code == 200
    assert all(w["currency"] == "USD" for w in r.json()["items"])
