import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.deps import auth as deps_auth
from app.rate_limit import client_ip_key


def _request(session: dict | None = None, headers: dict | None = None) -> Request:
    hdrs = []
    for k, v in (headers or {}).items():
        hdrs.append((k.lower().encode(), v.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": hdrs,
        "client": ("10.0.0.9", 12345),
        "server": ("testserver", 80),
        "session": session if session is not None else {},
    }
    return Request(scope)


class TestSessionHelpers:
    def test_set_and_clear_session(self, client_user):
        request = _request({})
        deps_auth.set_user_session(request, client_user)
        assert request.session[deps_auth.SESSION_USER_ID_KEY] == str(client_user.id)
        deps_auth.clear_user_session(request)
        assert request.session == {}

    def test_last_project_key(self):
        request = _request({})
        deps_auth.set_last_project_key(request, " demo ")
        assert deps_auth.get_last_project_key(request) == "DEMO"
        assert deps_auth.get_last_project_key(_request({})) is None

    def test_get_optional_user_id_invalid(self):
        request = _request({deps_auth.SESSION_USER_ID_KEY: "abc"})
        assert deps_auth.get_optional_user_id(request) is None

    def test_get_optional_user_missing(self, db_session):
        assert deps_auth.get_optional_user(_request({}), db_session) is None

    def test_get_optional_user_unknown_id(self, db_session):
        request = _request({deps_auth.SESSION_USER_ID_KEY: "99999"})
        assert deps_auth.get_optional_user(request, db_session) is None
        assert request.session == {}

    def test_get_optional_user_inactive(self, db_session, client_user):
        client_user.is_active = False
        db_session.commit()
        request = _request(
            {
                deps_auth.SESSION_USER_ID_KEY: str(client_user.id),
                deps_auth.SESSION_AUTH_EPOCH_KEY: int(client_user.auth_epoch or 0),
            }
        )
        assert deps_auth.get_optional_user(request, db_session) is None

    def test_get_optional_user_unactivated(self, db_session, client_user):
        client_user.activated_at = None
        db_session.commit()
        request = _request(
            {
                deps_auth.SESSION_USER_ID_KEY: str(client_user.id),
                deps_auth.SESSION_AUTH_EPOCH_KEY: int(client_user.auth_epoch or 0),
            }
        )
        assert deps_auth.get_optional_user(request, db_session) is None

    def test_get_optional_user_epoch_mismatch(self, db_session, client_user):
        request = _request(
            {
                deps_auth.SESSION_USER_ID_KEY: str(client_user.id),
                deps_auth.SESSION_AUTH_EPOCH_KEY: 999,
            }
        )
        assert deps_auth.get_optional_user(request, db_session) is None

    def test_get_optional_user_ok(self, db_session, client_user):
        request = _request(
            {
                deps_auth.SESSION_USER_ID_KEY: str(client_user.id),
                deps_auth.SESSION_AUTH_EPOCH_KEY: int(client_user.auth_epoch or 0),
            }
        )
        user = deps_auth.get_optional_user(request, db_session)
        assert user is not None
        assert user.id == client_user.id

    def test_require_user_unauthorized(self, db_session):
        with pytest.raises(HTTPException) as exc:
            deps_auth.require_user(_request({}), db_session)
        assert exc.value.status_code == 401

    def test_require_admin_forbidden(self, client_user):
        request = _request({})
        with pytest.raises(HTTPException) as exc:
            deps_auth.require_admin(request, client_user)
        assert exc.value.status_code == 403

    def test_require_admin_ok(self, admin_user):
        assert deps_auth.require_admin(_request({}), admin_user) is admin_user


class TestRateLimitKey:
    def test_without_proxy_headers(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("UVICORN_PROXY_HEADERS", "false")
        get_settings.cache_clear()
        try:
            assert client_ip_key(_request()) == "10.0.0.9"
        finally:
            get_settings.cache_clear()

    def test_with_xff(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("UVICORN_PROXY_HEADERS", "true")
        get_settings.cache_clear()
        try:
            ip = client_ip_key(
                _request(headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
            )
            assert ip == "1.2.3.4"
        finally:
            get_settings.cache_clear()
