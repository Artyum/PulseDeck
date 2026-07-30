"""Limitowanie częstotliwości żądań (SlowAPI)."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def client_ip_key(request: Request) -> str:
    from app.config import get_settings

    settings = get_settings()
    if settings.uvicorn_proxy_headers:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip() or get_remote_address(request)
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip_key)
