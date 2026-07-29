from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_FIELD_LABELS = {
    "user_id": "użytkownika",
    "content": "treści wiadomości",
    "title": "tytułu",
    "description": "opisu",
    "email": "adresu e-mail",
    "password": "hasła",
    "tag": "tagu",
}


def friendly_validation_message(exc: RequestValidationError) -> str:
    for err in exc.errors():
        loc = err.get("loc") or ()
        field = next(
            (str(x) for x in reversed(loc) if x not in ("body", "query", "path")),
            None,
        )
        typ = err.get("type", "")
        if typ == "missing":
            if field == "user_id":
                return "Wybierz użytkownika."
            label = _FIELD_LABELS.get(field or "", "wymaganego pola")
            return f"Brakuje {label}."
        if typ in {"int_parsing", "int_type"}:
            if field == "user_id":
                return "Wybierz użytkownika."
            return "Nieprawidłowa wartość liczbowa."
        msg = err.get("msg")
        if msg:
            return str(msg)
    return "Nieprawidłowe dane formularza."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {"detail": friendly_validation_message(exc)}, status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code in (401, 403) and not request.url.path.startswith("/api/"):
            if exc.status_code == 401:
                return RedirectResponse("/login", status_code=303)
            return (
                JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
                if request.headers.get("HX-Request")
                else RedirectResponse("/", status_code=303)
            )
        if exc.status_code == 404 and not request.url.path.startswith("/api/"):
            if request.headers.get("HX-Request"):
                return HTMLResponse("Nie znaleziono", status_code=404)
            return RedirectResponse("/", status_code=303)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
