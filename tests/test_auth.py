def test_register_and_login(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "Passw0rd123", "full_name": "Alice"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "user"
    assert "password" not in body and "password_hash" not in body

    r = client.post("/api/v1/auth/login", data={"username": "alice", "password": "Passw0rd123"})
    assert r.status_code == 200
    tokens = r.json()
    assert tokens["access_token"] and tokens["refresh_token"]


def test_register_rejects_weak_password(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "username": "bob", "password": "short"},
    )
    assert r.status_code == 422


def test_register_rejects_duplicate_email(client):
    payload = {"email": "dup@example.com", "username": "dup1", "password": "Passw0rd123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    payload["username"] = "dup2"
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409


def test_login_wrong_password(client):
    client.post("/api/v1/auth/register", json={"email": "c@example.com", "username": "carol", "password": "Passw0rd123"})
    r = client.post("/api/v1/auth/login", data={"username": "carol", "password": "WrongPass123"})
    assert r.status_code == 401


def test_login_unknown_username(client):
    r = client.post("/api/v1/auth/login", data={"username": "ghost", "password": "Passw0rd123"})
    assert r.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_token(client, auth):
    r = client.get("/api/v1/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_refresh_rotates_tokens(client):
    r = client.post("/api/v1/auth/register", json={"email": "d@example.com", "username": "dave", "password": "Passw0rd123"})
    login = client.post("/api/v1/auth/login", data={"username": "dave", "password": "Passw0rd123"}).json()

    r = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["access_token"] != login["access_token"]


def test_refresh_rejects_access_token_as_refresh(client, auth):
    access_token = auth["Authorization"].split(" ")[1]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert r.status_code == 401


def test_users_list_requires_support_role(client, auth):
    r = client.get("/api/v1/users", headers=auth)
    assert r.status_code == 403


def test_admin_can_list_and_deactivate_users(client, auth, admin_auth):
    r = client.get("/api/v1/users", headers=admin_auth)
    assert r.status_code == 200
    assert r.json()["total"] >= 2

    me = client.get("/api/v1/auth/me", headers=auth).json()
    r = client.post(f"/api/v1/users/{me['id']}/deactivate", headers=admin_auth)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # A deactivated user can no longer authenticate.
    r = client.post("/api/v1/auth/login", data={"username": "alice", "password": "Passw0rd123"})
    assert r.status_code == 401
