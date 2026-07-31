from __future__ import annotations

import logging
import secrets

from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import get_settings
from app.utils.csrf import CSRF_HEADER, CSRF_SESSION_KEY, ensure_csrf_token
from app.utils.i18n import resolve_lang, t

logger = logging.getLogger("pulsedeck.security")

_EXEMPT: tuple[tuple[str, str], ...] = (
    ("/auth/login", "POST"),
    ("/auth/forgot-password", "POST"),
    ("/auth/activate", "POST"),
    ("/email/unsubscribe", "POST"),
)


def _is_exempt(path: str, method: str) -> bool:
    return (path, method) in _EXEMPT


def _csrf_reject(request: Request, detail_key: str):
    lang = resolve_lang(request)
    detail = t(lang, detail_key)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=403, content={"detail": detail})
    hint = t(lang, "messages.csrf.refresh_hint")
    return HTMLResponse(
        status_code=403,
        content=f"<p>{detail} {hint}</p>",
    )


class CSRFProtectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.security_csrf_enabled:
            return await call_next(request)

        method = request.method.upper()
        path = request.url.path

        if method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return await call_next(request)

        if _is_exempt(path, method):
            return await call_next(request)

        ensure_csrf_token(request)
        session_token = request.session.get(CSRF_SESSION_KEY)
        token = request.headers.get(CSRF_HEADER)

        if not session_token or not token:
            logger.warning("CSRF: brak tokenu (path=%s method=%s)", path, method)
            return _csrf_reject(request, "messages.csrf.missing")

        try:
            ok = secrets.compare_digest(token, session_token)
        except (TypeError, ValueError):
            ok = False

        if not ok:
            logger.warning("CSRF: niezgodny token (path=%s method=%s)", path, method)
            return _csrf_reject(request, "messages.csrf.invalid")

        return await call_next(request)
