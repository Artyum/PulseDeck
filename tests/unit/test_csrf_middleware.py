import asyncio
from unittest.mock import AsyncMock

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.config import get_settings
from app.middleware.csrf import CSRFProtectMiddleware, _csrf_reject, _is_exempt
from app.utils.csrf import CSRF_HEADER, CSRF_SESSION_KEY


def _request(
    path: str = "/profile",
    method: str = "POST",
    *,
    session: dict | None = None,
    headers: dict | None = None,
) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "session": session if session is not None else {},
    }
    return Request(scope)


def _dispatch(request: Request):
    app = CSRFProtectMiddleware(app=AsyncMock())
    call_next = AsyncMock(return_value=PlainTextResponse("ok"))
    response = asyncio.run(app.dispatch(request, call_next))
    return response, call_next


class TestIsExempt:
    def test_login_post(self):
        assert _is_exempt("/auth/login", "POST") is True

    def test_open_reply_post_prefix(self):
        assert _is_exempt("/open/abcToken", "POST") is True
        assert _is_exempt("/open/abcToken", "GET") is False

    def test_other_path(self):
        assert _is_exempt("/profile", "POST") is False


class TestCsrfReject:
    def test_html_reject(self):
        response = _csrf_reject(_request("/profile"), "messages.csrf.missing")
        assert response.status_code == 403

    def test_api_json_reject(self):
        response = _csrf_reject(_request("/api/x"), "messages.csrf.invalid")
        assert response.status_code == 403


class TestCSRFProtectMiddleware:
    def test_disabled_passes(self, monkeypatch):
        monkeypatch.setenv("SECURITY_CSRF_ENABLED", "false")
        get_settings.cache_clear()
        try:
            response, call_next = _dispatch(_request())
            assert response.body == b"ok"
            call_next.assert_awaited_once()
        finally:
            get_settings.cache_clear()

    def test_get_passes_when_enabled(self, monkeypatch):
        monkeypatch.setenv("SECURITY_CSRF_ENABLED", "true")
        get_settings.cache_clear()
        try:
            response, call_next = _dispatch(_request(method="GET"))
            assert response.body == b"ok"
            call_next.assert_awaited_once()
        finally:
            get_settings.cache_clear()

    def test_exempt_login_passes(self, monkeypatch):
        monkeypatch.setenv("SECURITY_CSRF_ENABLED", "true")
        get_settings.cache_clear()
        try:
            response, call_next = _dispatch(_request("/auth/login", "POST"))
            assert response.body == b"ok"
            call_next.assert_awaited_once()
        finally:
            get_settings.cache_clear()

    def test_missing_token_rejected(self, monkeypatch):
        monkeypatch.setenv("SECURITY_CSRF_ENABLED", "true")
        get_settings.cache_clear()
        try:
            response, call_next = _dispatch(_request())
            assert response.status_code == 403
            call_next.assert_not_awaited()
        finally:
            get_settings.cache_clear()

    def test_invalid_token_rejected(self, monkeypatch):
        monkeypatch.setenv("SECURITY_CSRF_ENABLED", "true")
        get_settings.cache_clear()
        try:
            session = {CSRF_SESSION_KEY: "session-token"}
            response, call_next = _dispatch(
                _request(session=session, headers={CSRF_HEADER: "wrong"})
            )
            assert response.status_code == 403
            call_next.assert_not_awaited()
        finally:
            get_settings.cache_clear()

    def test_valid_token_passes(self, monkeypatch):
        monkeypatch.setenv("SECURITY_CSRF_ENABLED", "true")
        get_settings.cache_clear()
        try:
            token = "good-token"
            session = {CSRF_SESSION_KEY: token}
            response, call_next = _dispatch(
                _request(session=session, headers={CSRF_HEADER: token})
            )
            assert response.body == b"ok"
            call_next.assert_awaited_once()
        finally:
            get_settings.cache_clear()
