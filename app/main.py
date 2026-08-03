from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ExceptionHandler

from app.config import get_settings, project_root, resolve_upload_dir
from app.error_handlers import register_exception_handlers
from app.logging_setup import setup_logging
from app.middleware.csrf import CSRFProtectMiddleware
from app.middleware.security_headers import apply_security_headers
from app.middleware.session_sliding import SessionSlidingMiddleware
from app.rate_limit import client_ip_key, limiter
from app.routes import admin, auth, health, open_reply, portal
from app.utils.i18n import LANG_STORAGE_KEY, set_lang_cookie

logger = logging.getLogger("pulsedeck.app")
security_logger = logging.getLogger("pulsedeck.security")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    resolve_upload_dir()
    logger.info("PulseDeck started")
    yield
    logger.info("PulseDeck stopping")


def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    security_logger.warning(
        "Rate limit exceeded path=%s method=%s ip=%s",
        request.url.path,
        request.method,
        client_ip_key(request),
    )
    return _rate_limit_exceeded_handler(request, exc)


def build_fastapi_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="PulseDeck",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded, cast(ExceptionHandler, _rate_limit_handler)
    )
    register_exception_handlers(app)

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response = apply_security_headers(request, response)
        detected = getattr(request.state, "lang_from_accept", None)
        if detected and LANG_STORAGE_KEY not in request.cookies:
            set_lang_cookie(response, detected)
        return response

    hosts = settings.trusted_hosts_list()
    if settings.environment == "dev":
        hosts = list({*hosts, "testserver", "localhost", "127.0.0.1", "pulsedeck.lan"})
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(CSRFProtectMiddleware)
    app.add_middleware(SessionSlidingMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.storage_secret,
        session_cookie="pulsedeck_session",
        max_age=settings.session_max_age_seconds,
        same_site="lax",
        https_only=settings.environment == "prod",
    )

    mimetypes.add_type("application/manifest+json", ".webmanifest")
    static_dir = project_root() / "frontend" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(portal.router)
    app.include_router(open_reply.router)
    return app


fastapi_app = build_fastapi_app()
