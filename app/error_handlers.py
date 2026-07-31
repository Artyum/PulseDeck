from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routes.context import render
from app.utils.i18n import resolve_lang, t

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
        if exc.status_code in (401, 403) and not request.url.path.startswith("/api/"):
            if exc.status_code == 401:
                return RedirectResponse("/login", status_code=303)
            if request.headers.get("HX-Request"):
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            return RedirectResponse("/", status_code=303)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
