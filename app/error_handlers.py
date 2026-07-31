from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from app.routes.context import render
from app.utils.i18n import resolve_lang, t

logger = logging.getLogger("pulsedeck.app")

_FIELD_KEYS = frozenset(
    {"user_id", "content", "title", "description", "email", "password", "tag"}
)


def friendly_validation_message(exc: RequestValidationError, lang: str) -> str:
    for err in exc.errors():
        loc = err.get("loc") or ()
        field = next(
            (str(x) for x in reversed(loc) if x not in ("body", "query", "path")),
            None,
        )
        typ = err.get("type", "")
        if typ == "missing":
            if field == "user_id":
                return t(lang, "messages.validation.missing_user")
            label_key = (
                f"messages.validation.field.{field}"
                if field in _FIELD_KEYS
                else "messages.validation.field.required"
            )
            return t(
                lang,
                "messages.validation.missing_field",
                label=t(lang, label_key),
            )
        if typ in {"int_parsing", "int_type"}:
            if field == "user_id":
                return t(lang, "messages.validation.missing_user")
            return t(lang, "messages.validation.invalid_int")
        msg = err.get("msg")
        if msg:
            return str(msg)
    return t(lang, "messages.validation.invalid_form")


def _not_found_response(request: Request):
    lang = resolve_lang(request)
    message = t(lang, "messages.http.not_found")
    path = request.url.path
    if path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=404)
    if request.headers.get("HX-Request"):
        return HTMLResponse(message, status_code=404)
    if request.method in ("GET", "HEAD"):
        return render(request, "errors/404.html", status_code=404)
    return JSONResponse({"detail": message}, status_code=404)


def _server_error_response(request: Request):
    lang = resolve_lang(request)
    message = t(lang, "messages.http.server_error")
    if request.url.path.startswith("/api/") or request.headers.get("HX-Request"):
        return JSONResponse({"detail": message}, status_code=500)
    return HTMLResponse(f"<p>{message}</p>", status_code=500)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError):
        if any((err.get("loc") or ())[:1] == ("path",) for err in exc.errors()):
            return _not_found_response(request)
        lang = resolve_lang(request)
        return JSONResponse(
            {"detail": friendly_validation_message(exc, lang)}, status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _not_found_response(request)
        if exc.status_code >= 500:
            logger.error(
                "HTTP %s %s %s detail=%s",
                exc.status_code,
                request.method,
                request.url.path,
                exc.detail,
            )
        if exc.status_code in (401, 403) and not request.url.path.startswith("/api/"):
            if exc.status_code == 401:
                return RedirectResponse("/login", status_code=303)
            if request.headers.get("HX-Request"):
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            return RedirectResponse("/", status_code=303)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(request: Request, exc: Exception):
        if isinstance(exc, ClientDisconnect):
            return Response(status_code=400)
        logger.exception("Unhandled exception %s %s", request.method, request.url.path)
        return _server_error_response(request)
