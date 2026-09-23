from tests.helpers import login, login_client, make_user


def _enable_mfa(monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "mfa_enabled", True)


def test_login_without_mfa_redirects(client, client_user):
    r = login_client(client)
    assert r.status_code == 303


def test_mfa_required_then_verify(client, db_session, monkeypatch):
    make_user(
        db_session,
        "mfa-user@test.local",
        first_name="Mfa",
        last_name="User",
        password="Client123!ab",
        activated=True,
        is_active=True,
    )
    _enable_mfa(monkeypatch)
    monkeypatch.setattr("app.services.mfa.generate_code", lambda: "123456")
    first = login(client, "mfa-user@test.local", "Client123!ab", assert_ok=False)
    assert first.status_code == 200
    assert "mfa-digit" in first.text
    home = client.get("/", follow_redirects=False)
    assert home.status_code in (303, 302)
    verify = client.post(
        "/auth/mfa/verify",
        data={
            "d0": "1",
            "d1": "2",
            "d2": "3",
            "d3": "4",
            "d4": "5",
            "d5": "6",
            "trust_device": "on",
        },
        follow_redirects=False,
    )
    assert verify.status_code == 303
    client.post("/auth/logout", follow_redirects=False)
    again = login(client, "mfa-user@test.local", "Client123!ab", assert_ok=False)
    assert again.status_code == 303


def test_mfa_queue_failure_shows_error(client, db_session, monkeypatch):
    make_user(
        db_session,
        "mfa-fail@test.local",
        first_name="Mfa",
        last_name="Fail",
        password="Client123!ab",
        activated=True,
        is_active=True,
    )
    _enable_mfa(monkeypatch)
    monkeypatch.setattr("app.services.mfa.generate_code", lambda: "123456")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("queue down")

    monkeypatch.setattr("app.services.mfa.enqueue_email", _boom)
    first = login(client, "mfa-fail@test.local", "Client123!ab", assert_ok=False)
    assert first.status_code == 200
    assert (
        "Nie udało się wysłać kodu" in first.text
        or "Could not send the code" in first.text
    )
    home = client.get("/", follow_redirects=False)
    assert home.status_code in (303, 302)
