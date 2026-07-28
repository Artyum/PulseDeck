"""Ochrona CSRF dla żądań modyfikujących stan."""

from __future__ import annotations

import logging
import secrets

from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import get_settings
from app.utils.csrf import CSRF_HEADER, CSRF_SESSION_KEY, ensure_csrf_token

logger = logging.getLogger("pulsedeck.middleware.csrf")

_EXEMPT: tuple[tuple[str, str], ...] = (
    ("/auth/login", "POST"),
    ("/auth/magic", "POST"),
    ("/auth/set-password", "POST"),
)


def _is_exempt(path: str, method: str) -> bool:
    if (path, method) in _EXEMPT:
        return True
    return method == "POST" and path.startswith("/invite/")


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
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=403, content={"detail": "Brak lub nieważny token CSRF."}
                )
            return HTMLResponse(
                status_code=403,
                content="<p>Brak lub nieważny token CSRF. Odśwież stronę i spróbuj ponownie.</p>",
            )

        try:
            ok = secrets.compare_digest(token, session_token)
        except (TypeError, ValueError):
            ok = False

        if not ok:
            logger.warning("CSRF: niezgodny token (path=%s method=%s)", path, method)
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=403, content={"detail": "Nieważny token CSRF."}
                )
            return HTMLResponse(
                status_code=403,
                content="<p>Nieważny token CSRF. Odśwież stronę i spróbuj ponownie.</p>",
            )

        return await call_next(request)
