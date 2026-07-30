"""Tests for error handling: 404, 403, 401 responses."""


def test_404_api(client):
    r = client.get("/api/nonexistent")
    assert r.status_code == 404


def test_404_page_redirect(client):
    r = client.get("/nonexistent-page", follow_redirects=False)
    assert r.status_code in (303, 404)


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_protected_endpoint_without_login(client):
    r = client.get("/profile", follow_redirects=False)
    assert r.status_code in (303, 401)
