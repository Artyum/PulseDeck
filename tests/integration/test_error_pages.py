"""Tests for error handling: 404, 403, 401 responses."""

from tests.helpers import login, login_admin


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
    login_admin(client)
    r = client.get("/admin/users/aa", follow_redirects=False)
    assert r.status_code == 404
    assert "text/html" in r.headers.get("content-type", "")
    assert b'"detail"' not in r.content


def test_404_missing_user(client, admin_user):
    login_admin(client)
    r = client.get("/admin/users/999999999", follow_redirects=False)
    assert r.status_code == 404
    assert "text/html" in r.headers.get("content-type", "")


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_protected_endpoint_without_login(client):
    r = client.get("/profile", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=/profile"


def test_ticket_without_login_returns_to_ticket(client):
    r = client.get("/t/DEMO-1", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=/t/DEMO-1"


def test_login_with_next_opens_ticket(client, client_user):
    dest = "/t/DEMO-1"
    r = login(client, client_user.email, "Client123!ab", next_path=dest)
    assert r.headers["location"] == dest
