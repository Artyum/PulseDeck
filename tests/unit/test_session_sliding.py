import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.config import get_settings
from app.middleware.session_sliding import (
    SESSION_ACTIVITY_KEY,
    SessionSlidingMiddleware,
)


def _request(session: dict[str, Any], path: str = "/") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
        "session": session,
    }
    return Request(scope)


def _dispatch(request: Request):
    mw = SessionSlidingMiddleware(app=AsyncMock())
    call_next = AsyncMock(return_value=PlainTextResponse("ok"))
    return asyncio.run(mw.dispatch(request, call_next))


class TestSessionSliding:
    def test_sets_activity_for_logged_in(self):
        session = {"user_id": "1"}
        _dispatch(_request(session))
        assert SESSION_ACTIVITY_KEY in session

    def test_refreshes_activity(self):
        now = int(time.time())
        session = {"user_id": "1", SESSION_ACTIVITY_KEY: now - 10}
        _dispatch(_request(session))
        assert session[SESSION_ACTIVITY_KEY] >= now - 1

    def test_clears_expired_session(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "session_max_age_seconds", 30)
        session = {
            "user_id": "1",
            SESSION_ACTIVITY_KEY: int(time.time()) - 100,
        }
        _dispatch(_request(session))
        assert session == {}

    def test_invalid_last_clears(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "session_max_age_seconds", 30)
        session = {"user_id": "1", SESSION_ACTIVITY_KEY: "bad"}
        _dispatch(_request(session))
        assert session == {}

    def test_anonymous_untouched(self):
        session = {}
        _dispatch(_request(session))
        assert SESSION_ACTIVITY_KEY not in session

    def test_static_path_skips(self):
        now = int(time.time()) - 10
        session = {"user_id": "1", SESSION_ACTIVITY_KEY: now}
        _dispatch(_request(session, path="/static/app.js"))
        assert session[SESSION_ACTIVITY_KEY] == now
