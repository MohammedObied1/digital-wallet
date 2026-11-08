import os

os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _fresh_db():
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register_and_login(
    client: TestClient, username: str = "alice", email: str | None = None, password: str = "Passw0rd123"
) -> dict[str, str]:
    payload = {"email": email or f"{username}@example.com", "username": username, "password": password, "full_name": username.title()}
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    tokens = r.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}, tokens


@pytest.fixture
def auth(client):
    headers, _ = register_and_login(client, "alice")
    return headers


@pytest.fixture
def auth_bob(client):
    headers, _ = register_and_login(client, "bob")
    return headers


@pytest.fixture
def admin_auth(client):
    from app.models import User, UserRole

    headers, _tokens = register_and_login(client, "admin_user", password="AdminPass123")
    db = TestingSession()
    try:
        user = db.query(User).filter(User.username == "admin_user").one()
        user.role = UserRole.ADMIN
        db.commit()
    finally:
        db.close()
    # Role is looked up from the DB on every request (see deps.get_current_user), so the
    # already-issued access token remains valid after promoting the user to admin here.
    return headers
