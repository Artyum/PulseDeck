"""Tests for error handling: 404, 403, 401 responses."""


def _login_admin(client):
    r = client.post(
        "/auth/login",
        data={"email": "admin@test.local", "password": "Admin123!abcd"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 200)


def test_404_api(client):
    r = client.get("/api/nonexistent")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_404_page(client):
    r = client.get("/nonexistent-page", follow_redirects=False)
    assert r.status_code == 404
    assert "text/html" in r.headers.get("content-type", "")
    assert b"404" in r.content


def test_404_invalid_path_param(client, admin_user):
    _login_admin(client)
    r = client.get("/admin/users/aa", follow_redirects=False)
    assert r.status_code == 404
    assert "text/html" in r.headers.get("content-type", "")
    assert b'"detail"' not in r.content


def test_404_missing_user(client, admin_user):
    _login_admin(client)
    r = client.get("/admin/users/999999999", follow_redirects=False)
    assert r.status_code == 404
    assert "text/html" in r.headers.get("content-type", "")


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_protected_endpoint_without_login(client):
    r = client.get("/profile", follow_redirects=False)
    assert r.status_code in (303, 401)
