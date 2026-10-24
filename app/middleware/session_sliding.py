"""Przedłużanie sesji przy aktywności zalogowanego użytkownika."""

from __future__ import annotations

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import get_settings

SESSION_ACTIVITY_KEY = "_last_activity"
_SKIP_PREFIXES: tuple[str, ...] = ("/static/", "/uploads/")


def _is_logged_in(session: dict[str, Any]) -> bool:
    return bool(session.get("user_id"))


def _session_max_age() -> int:
    return get_settings().session_max_age_seconds


class SessionSlidingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if "session" not in request.scope:
            return await call_next(request)
        if request.url.path.startswith(_SKIP_PREFIXES):
            return await call_next(request)

        session = request.session
        if not _is_logged_in(session):
            return await call_next(request)

        now = int(time.time())
        last = session.get(SESSION_ACTIVITY_KEY)
        max_age = _session_max_age()
        try:
            age = now - int(last) if last is not None else 0
        except (TypeError, ValueError):
            age = max_age + 1
        if last is not None and age > max_age:
            session.clear()
        else:
            session[SESSION_ACTIVITY_KEY] = now
        return await call_next(request)
