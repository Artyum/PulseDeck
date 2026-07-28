from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.deps.auth import (
    CurrentUser,
    DbSession,
    clear_user_session,
    get_optional_user,
    set_user_session,
)
from app.models.enums import MagicTokenPurpose
from app.models.user import User
from app.rate_limit import limiter
from app.routes.context import render
from app.services import auth as auth_service
from app.services.email import notify_email_confirm, notify_magic_link
from app.utils.password import verify_password

router = APIRouter(tags=["auth"])


def _render_login(
    request: Request,
    *,
    error: str | None = None,
    magic_sent: bool = False,
    success: str | None = None,
):
    return render(
        request,
        "auth/login.html",
        error=error,
        magic_sent=magic_sent,
        success=success,
    )


def _render_profile(
    request: Request,
    user: User,
    *,
    error: str | None = None,
    success: str | None = None,
):
    return render(
        request,
        "auth/profile.html",
        user=user,
        edit_user=user,
        is_admin_edit=False,
        form_action="/profile",
        error=error,
        success=success,
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: DbSession):
    user = get_optional_user(request, db)
    if user:
        return RedirectResponse("/", status_code=303)
    return _render_login(request)


@router.post("/auth/login")
@limiter.limit("10/minute")
def login_submit(
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    user = auth_service.authenticate_password(db, email, password)
    if not user:
        return _render_login(request, error="Nieprawidłowy e-mail lub hasło.")
    blocked = auth_service.login_blocked_reason(user)
    if blocked:
        return _render_login(request, error=blocked)
    set_user_session(request, user)
    return RedirectResponse("/", status_code=303)


@router.post("/auth/magic")
@limiter.limit("10/minute")
def magic_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbSession,
    email: Annotated[str, Form()],
):
    user = auth_service.get_user_by_email(db, email)
    if user and not auth_service.login_blocked_reason(user):
        token_row = auth_service.create_magic_token(
            db, user, purpose=MagicTokenPurpose.LOGIN
        )
        notify_magic_link(background_tasks, user, token_row.token)
    return _render_login(request, magic_sent=True)


@router.get("/auth/verify")
def verify_magic(request: Request, token: str, db: DbSession):
    row = auth_service.peek_magic_token(db, token, purpose=MagicTokenPurpose.LOGIN)
    if not row:
        return _render_login(request, error="Link jest nieważny lub wygasł.")
    user = db.get(User, row.user_id)
    if not user or auth_service.login_blocked_reason(user):
        return _render_login(request, error="Link jest nieważny lub wygasł.")
    row.used = True
    db.commit()
    set_user_session(request, user)
    return RedirectResponse("/", status_code=303)


@router.post("/auth/logout")
def logout(request: Request):
    clear_user_session(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, user: CurrentUser):
    return _render_profile(request, user)


@router.post("/profile")
def update_profile(
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    phone: Annotated[str, Form()] = "",
):
    try:
        auth_service.update_profile_fields(
            db, user, first_name=first_name, last_name=last_name, phone=phone
        )
        new_email = auth_service.normalize_email(email)
        if new_email != user.email:
            token_row = auth_service.request_email_change(db, user, new_email)
            notify_email_confirm(background_tasks, user, token_row.token, new_email)
            clear_user_session(request)
            return RedirectResponse("/login?email_confirm=1", status_code=303)
        db.commit()
        db.refresh(user)
    except ValueError as exc:
        db.rollback()
        return _render_profile(request, user, error=str(exc))
    return _render_profile(request, user, success="Profil został zaktualizowany.")


@router.post("/profile/password")
def change_password(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
):
    if new_password != confirm_password:
        return _render_profile(request, user, error="Hasła nie są zgodne.")
    if not user.password_hash or not verify_password(
        current_password, user.password_hash
    ):
        return _render_profile(request, user, error="Obecne hasło jest nieprawidłowe.")
    try:
        auth_service.set_password(user, new_password)
        db.commit()
    except ValueError as exc:
        return _render_profile(request, user, error=str(exc))
    return _render_profile(request, user, success="Hasło zostało zmienione.")


@router.get("/auth/confirm-email")
def confirm_email(request: Request, token: str, db: DbSession):
    user = auth_service.confirm_email_change(db, token)
    if not user:
        return _render_login(
            request, error="Link potwierdzający jest nieważny lub wygasł."
        )
    return _render_login(
        request,
        success="E-mail został potwierdzony. Zaloguj się nowym adresem.",
    )


@router.get("/auth/set-password", response_class=HTMLResponse)
def set_password_page(request: Request, token: str, db: DbSession):
    row = auth_service.peek_magic_token(
        db, token, purpose=MagicTokenPurpose.PASSWORD_SET
    )
    if not row:
        return _render_login(
            request, error="Link do ustawienia hasła jest nieważny lub wygasł."
        )
    return render(request, "auth/set_password.html", token=token, error=None)


@router.post("/auth/set-password")
@limiter.limit("10/minute")
def set_password_submit(
    request: Request,
    db: DbSession,
    token: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
):
    if new_password != confirm_password:
        return render(
            request,
            "auth/set_password.html",
            token=token,
            error="Hasła nie są zgodne.",
        )
    try:
        user = auth_service.complete_password_set(db, token, new_password)
    except ValueError as exc:
        return render(
            request,
            "auth/set_password.html",
            token=token,
            error=str(exc),
        )
    if not user:
        return _render_login(
            request, error="Link do ustawienia hasła jest nieważny lub wygasł."
        )
    set_user_session(request, user)
    return RedirectResponse("/", status_code=303)
