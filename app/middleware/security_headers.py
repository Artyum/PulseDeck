"""Nagłówki bezpieczeństwa."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings


def _request_is_https(request: Request) -> bool:
    proto = (
        request.headers.get("x-forwarded-proto") or request.url.scheme or ""
    ).lower()
    return proto == "https"


def _request_is_secure_context(request: Request) -> bool:
    if _request_is_https(request):
        return True
    host = (request.url.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    return host.endswith(".localhost")


def _content_security_policy(*, upgrade_insecure: bool = False) -> str:
    policy = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval'; "
        "script-src-attr 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    if upgrade_insecure:
        policy += "; upgrade-insecure-requests"
    return policy


def apply_security_headers(request: Request, response: Response) -> Response:
    settings = get_settings()
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    path = request.url.path
    if path.startswith("/open/"):
        response.headers["Referrer-Policy"] = "no-referrer"
    else:
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
    response.headers.setdefault(
        "Permissions-Policy",
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
    )
    if _request_is_secure_context(request):
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if settings.security_csp_enabled:
        response.headers.setdefault(
            "Content-Security-Policy",
            _content_security_policy(upgrade_insecure=_request_is_https(request)),
        )
    if settings.security_hsts_enabled and _request_is_https(request):
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    if path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif (response.headers.get("content-type") or "").lower().startswith("text/html"):
        response.headers["Cache-Control"] = "no-store"
    return response
