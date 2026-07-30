from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.deps.auth import (
    CurrentUser,
    DbSession,
    clear_user_session,
    get_optional_user,
    set_user_session,
)
from app.models.user import User
from app.rate_limit import limiter
from app.routes.context import render
from app.services import auth as auth_service
from app.services.email import notify_email_confirm
from app.utils.i18n import resolve_lang, t
from app.utils.password import verify_password

router = APIRouter(tags=["auth"])


def _login_limit() -> str:
    return get_settings().auth_login_rate_limit


def _forgot_limit() -> str:
    return get_settings().auth_forgot_password_rate_limit


def _activate_limit() -> str:
    return get_settings().auth_activate_rate_limit


def _render_login(
    request: Request,
    *,
    error: str | None = None,
    success: str | None = None,
    forgot_sent: bool = False,
):
    return render(
        request,
        "auth/login.html",
        error=error,
        success=success,
        forgot_sent=forgot_sent,
    )


def _render_profile(
    request: Request,
    user: User,
    *,
    section: str = "dane",
    error: str | None = None,
    success: str | None = None,
):
    if section not in ("dane", "password", "settings"):
        section = "dane"
    return render(
        request,
        "auth/profile.html",
        user=user,
        edit_user=user,
        is_admin_edit=False,
        profile_section=section,
        error=error,
        success=success,
    )


def _render_activate(
    request: Request,
    *,
    token: str,
    pending: bool,
    error: str | None = None,
):
    return render(
        request,
        "auth/activate.html",
        token=token,
        pending=pending,
        error=error,
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: DbSession):
    user = get_optional_user(request, db)
    if user:
        return RedirectResponse("/", status_code=303)
    return _render_login(request)


@router.post("/auth/login")
@limiter.limit(_login_limit)
def login_submit(
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    user = auth_service.authenticate_password(db, email, password)
    if not user:
        return _render_login(
            request, error=t(lang, "flash.auth.invalid_credentials")
        )
    blocked = auth_service.login_blocked_reason(user, lang=lang)
    if blocked:
        return _render_login(request, error=blocked)
    set_user_session(request, user)
    return RedirectResponse("/", status_code=303)


@router.post("/auth/forgot-password")
@limiter.limit(_forgot_limit)
def forgot_password(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbSession,
    email: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    user = auth_service.get_user_by_email(db, email)
    if user and auth_service.can_receive_password_link(user):
        auth_service.send_password_link(db, background_tasks, user, lang=lang)
    return _render_login(request, forgot_sent=True)


@router.post("/auth/logout")
def logout(request: Request):
    clear_user_session(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, user: CurrentUser):
    return _render_profile(request, user, section="dane")


@router.get("/profile/password", response_class=HTMLResponse)
def profile_password_page(request: Request, user: CurrentUser):
    return _render_profile(request, user, section="password")


@router.get("/profile/settings", response_class=HTMLResponse)
def profile_settings_page(request: Request, user: CurrentUser):
    return _render_profile(request, user, section="settings")


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
    lang = resolve_lang(request)
    try:
        auth_service.update_profile_fields(
            db,
            user,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            lang=lang,
        )
        new_email = auth_service.normalize_email(email)
        if new_email != user.email:
            token_row = auth_service.request_email_change(
                db, user, new_email, lang=lang
            )
            notify_email_confirm(
                background_tasks, user, token_row.token, new_email, lang=lang
            )
            clear_user_session(request)
            return RedirectResponse("/login?email_confirm=1", status_code=303)
        db.commit()
        db.refresh(user)
    except ValueError as exc:
        db.rollback()
        return _render_profile(request, user, section="dane", error=str(exc))
    return _render_profile(
        request, user, section="dane", success=t(lang, "flash.auth.profile_updated")
    )


@router.post("/profile/password")
def change_password(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    try:
        auth_service.require_matching_passwords(
            new_password, confirm_password, lang=lang
        )
        if not user.password_hash or not verify_password(
            current_password, user.password_hash
        ):
            raise ValueError(t(lang, "flash.auth.current_password_invalid"))
        auth_service.set_password(user, new_password, lang=lang)
        db.commit()
    except ValueError as exc:
        return _render_profile(request, user, section="password", error=str(exc))
    return _render_profile(
        request,
        user,
        section="password",
        success=t(lang, "flash.auth.password_changed"),
    )


@router.get("/auth/confirm-email")
def confirm_email(request: Request, token: str, db: DbSession):
    lang = resolve_lang(request)
    user = auth_service.confirm_email_change(db, token)
    if not user:
        return _render_login(
            request, error=t(lang, "flash.auth.confirm_link_invalid")
        )
    return _render_login(
        request,
        success=t(lang, "flash.auth.email_confirmed"),
    )


@router.get("/auth/activate", response_class=HTMLResponse)
def activate_page(request: Request, token: str, db: DbSession):
    lang = resolve_lang(request)
    resolved = auth_service.resolve_password_set_token(db, token)
    if not resolved:
        return _render_login(
            request, error=t(lang, "flash.auth.activation_link_invalid")
        )
    _, user = resolved
    return _render_activate(request, token=token, pending=user.is_pending)


@router.get("/auth/set-password")
def set_password_redirect(token: str):
    return RedirectResponse(f"/auth/activate?token={token}", status_code=303)


@router.post("/auth/activate")
@limiter.limit(_activate_limit)
def activate_submit(
    request: Request,
    db: DbSession,
    token: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    phone: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    resolved = auth_service.resolve_password_set_token(db, token)
    pending = bool(resolved and resolved[1].is_pending)
    try:
        auth_service.require_matching_passwords(
            new_password, confirm_password, lang=lang
        )
        user = auth_service.complete_password_set(
            db,
            token,
            new_password,
            phone=phone if pending else None,
            lang=lang,
        )
    except ValueError as exc:
        return _render_activate(request, token=token, pending=pending, error=str(exc))
    if not user:
        return _render_login(
            request, error=t(lang, "flash.auth.activation_link_invalid")
        )
    set_user_session(request, user)
    return RedirectResponse("/", status_code=303)
