def test_ensure_csrf_token_disabled_when_config_off(monkeypatch):
    monkeypatch.setenv("SECURITY_CSRF_ENABLED", "false")
    from app.utils.csrf import ensure_csrf_token

    request = type("Request", (), {"session": {}})()
    assert ensure_csrf_token(request) == ""


def test_ensure_csrf_token_creates_new(monkeypatch):
    monkeypatch.setenv("SECURITY_CSRF_ENABLED", "true")
    # Need to clear cached settings
    from app.config import get_settings
    get_settings.cache_clear()

    from app.utils.csrf import ensure_csrf_token

    session = {}
    request = type("Request", (), {"session": session})()
    token = ensure_csrf_token(request)
    assert token
    assert isinstance(token, str)
    assert session["_csrf_token"] == token


def test_ensure_csrf_token_returns_existing(monkeypatch):
    monkeypatch.setenv("SECURITY_CSRF_ENABLED", "true")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.utils.csrf import ensure_csrf_token

    session = {"_csrf_token": "existing-token"}
    request = type("Request", (), {"session": session})()
    assert ensure_csrf_token(request) == "existing-token"
