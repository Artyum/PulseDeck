"""Token CSRF przechowywany w podpisanej sesji (cookie)."""

from __future__ import annotations

import secrets

from starlette.requests import Request

CSRF_SESSION_KEY = "_csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def ensure_csrf_token(request: Request) -> str:
    from app.config import get_settings

    if not get_settings().security_csrf_enabled:
        return ""
    token = request.session.get(CSRF_SESSION_KEY)
    if not token or not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token
