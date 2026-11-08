def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_versioned_liveness(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_versioned_readiness(client):
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["database"] == "connected"
