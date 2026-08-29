"""Przedłużanie sesji przy aktywności."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import get_settings

SESSION_ACTIVITY_KEY = "_last_activity"


class SessionSlidingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if "session" in request.scope:
            now = int(time.time())
            last = request.session.get(SESSION_ACTIVITY_KEY)
            if last is not None:
                try:
                    age = now - int(last)
                except (TypeError, ValueError):
                    age = settings.session_max_age_seconds + 1
                if age > settings.session_max_age_seconds:
                    request.session.clear()
                else:
                    request.session[SESSION_ACTIVITY_KEY] = now
            elif request.session.get("user_id"):
                request.session[SESSION_ACTIVITY_KEY] = now
        return await call_next(request)
