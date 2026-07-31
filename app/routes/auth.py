from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.responses import Response

from app.config import get_settings
from app.deps.auth import (
    CurrentUser,
    DbSession,
    clear_user_session,
    get_optional_user,
    set_user_session,
)
from app.models.enums import MagicTokenPurpose
from app.models.user import User
from app.rate_limit import client_ip_key, limiter
from app.routes.context import render
from app.services import auth as auth_service
from app.services.email import notify_email_confirm
from app.utils.csrf import ensure_csrf_token
from app.utils.i18n import (
    LANG_STORAGE_KEY,
    available_lang_ids,
    normalize_lang,
    resolve_lang,
    t,
)
from app.utils.password import verify_password
from app.utils.unsubscribe import apply_unsubscribe, parse_unsubscribe_token

router = APIRouter(tags=["auth"])
logger = logging.getLogger("pulsedeck.auth")

_LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 5


def _set_lang_cookie(response: Response, lang: str) -> None:
    response.set_cookie(
        LANG_STORAGE_KEY,
        normalize_lang(lang),
        max_age=_LANG_COOKIE_MAX_AGE,
        path="/",
        samesite="lax",
    )


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
    section: str = "profile",
    error: str | None = None,
    success: str | None = None,
):
    if section not in ("profile", "data", "password", "notifications", "appearance"):
        section = "profile"
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
    ip = client_ip_key(request)
    email_norm = email.strip().lower()
    user = auth_service.authenticate_password(db, email, password)
    if not user:
        logger.warning("Login failed email=%s ip=%s", email_norm, ip)
        return _render_login(request, error=t(lang, "flash.auth.invalid_credentials"))
    blocked = auth_service.login_blocked_reason(user, lang=lang)
    if blocked:
        logger.warning("Login blocked email=%s ip=%s", email_norm, ip)
        return _render_login(request, error=blocked)
    clear_user_session(request, preserve_last_project=True)
    set_user_session(request, user)
    ensure_csrf_token(request)
    cookie_lang = (request.cookies.get(LANG_STORAGE_KEY) or "").strip().lower()
    response = RedirectResponse("/", status_code=303)
    if cookie_lang in available_lang_ids():
        if cookie_lang != user.ui_lang:
            auth_service.update_ui_lang(db, user, cookie_lang)
    else:
        _set_lang_cookie(response, user.ui_lang)
    logger.info("Login ok email=%s user_id=%s ip=%s", user.email, user.id, ip)
    return response


@router.post("/auth/forgot-password")
@limiter.limit(_forgot_limit)
def forgot_password(
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    user = auth_service.get_user_by_email(db, email)
    if user and auth_service.can_receive_password_link(user):
        auth_service.send_password_link(db, user, lang=lang)
        logger.info("Password reset link sent user_id=%s email=%s", user.id, user.email)
    return _render_login(request, forgot_sent=True)


@router.post("/auth/logout")
def logout(request: Request):
    user_id = request.session.get("user_id")
    clear_user_session(request, preserve_last_project=True)
    if user_id is not None:
        logger.info("Logout user_id=%s", user_id)
    return RedirectResponse("/login", status_code=303)


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, user: CurrentUser):
    return _render_profile(request, user, section="profile")


@router.get("/profile/data", response_class=HTMLResponse)
def profile_data_page(request: Request, user: CurrentUser):
    return _render_profile(request, user, section="data")


@router.get("/profile/password", response_class=HTMLResponse)
def profile_password_page(request: Request, user: CurrentUser):
    return _render_profile(request, user, section="password")


@router.get("/profile/notifications", response_class=HTMLResponse)
def profile_notifications_page(request: Request, user: CurrentUser):
    return _render_profile(request, user, section="notifications")


@router.get("/profile/appearance", response_class=HTMLResponse)
def profile_appearance_page(request: Request, user: CurrentUser):
    return _render_profile(request, user, section="appearance")


@router.post("/profile/data")
def update_profile(
    request: Request,
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
        success_key = "flash.auth.profile_updated"
        if new_email != user.email:
            _, raw = auth_service.request_email_change(db, user, new_email, lang=lang)
            notify_email_confirm(db, user, raw, new_email)
            success_key = "flash.auth.email_confirm_sent"
        else:
            db.commit()
        db.refresh(user)
    except ValueError as exc:
        db.rollback()
        return _render_profile(request, user, section="data", error=str(exc))
    return _render_profile(request, user, section="data", success=t(lang, success_key))


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
        auth_service.bump_auth_epoch(user)
        db.commit()
        db.refresh(user)
        set_user_session(request, user)
    except ValueError as exc:
        return _render_profile(request, user, section="password", error=str(exc))
    return _render_profile(
        request,
        user,
        section="password",
        success=t(lang, "flash.auth.password_changed"),
    )


@router.post("/profile/notifications")
def update_notifications(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    notify_new_ticket: Annotated[str, Form()] = "",
    notify_reply: Annotated[str, Form()] = "",
    notify_ticket_update: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    auth_service.update_notification_prefs(
        db,
        user,
        notify_new_ticket=bool(notify_new_ticket),
        notify_reply=bool(notify_reply),
        notify_ticket_update=bool(notify_ticket_update),
    )
    return _render_profile(
        request,
        user,
        section="notifications",
        success=t(lang, "flash.auth.notifications_updated"),
    )


@router.post("/profile/language")
def update_language(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    lang: Annotated[str, Form()],
):
    auth_service.update_ui_lang(db, user, lang)
    response = PlainTextResponse("ok")
    _set_lang_cookie(response, lang)
    return response


@router.post("/profile/datetime-prefs")
def update_datetime_prefs(
    user: CurrentUser,
    db: DbSession,
    datetime_format: Annotated[str, Form()],
    timezone: Annotated[str, Form()],
):
    auth_service.update_datetime_prefs(
        db,
        user,
        datetime_format=datetime_format,
        timezone=timezone,
    )
    return PlainTextResponse("ok")


@router.post("/profile/datetime-prefs-auto")
def update_datetime_prefs_auto(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    timezone: Annotated[str, Form()],
    datetime_format: Annotated[str, Form()],
    lang: Annotated[str, Form()] = "",
):
    cookie_lang = (request.cookies.get(LANG_STORAGE_KEY) or "").strip().lower()
    lang_raw = (lang or "").strip().lower()
    ui_lang = None
    if cookie_lang not in available_lang_ids() and lang_raw in available_lang_ids():
        ui_lang = lang_raw
    changed = auth_service.apply_auto_datetime_prefs(
        db,
        user,
        timezone=timezone,
        datetime_format=datetime_format,
        ui_lang=ui_lang,
    )
    if not changed:
        return Response(status_code=204)
    response = PlainTextResponse("ok")
    if ui_lang:
        _set_lang_cookie(response, ui_lang)
    return response


def _render_confirm_email(
    request: Request,
    *,
    token: str,
    error: str | None = None,
):
    return render(
        request,
        "auth/confirm_email.html",
        token=token,
        error=error,
    )


@router.get("/auth/confirm-email", response_class=HTMLResponse)
def confirm_email_page(request: Request, token: str, db: DbSession):
    lang = resolve_lang(request)
    row = auth_service.peek_magic_token(
        db, token, purpose=MagicTokenPurpose.EMAIL_CONFIRM
    )
    if not row:
        return _render_login(request, error=t(lang, "flash.auth.confirm_link_invalid"))
    return _render_confirm_email(request, token=token)


@router.post("/auth/confirm-email")
def confirm_email_submit(
    request: Request,
    db: DbSession,
    token: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    user = auth_service.confirm_email_change(db, token)
    if not user:
        logger.warning("Email confirm failed invalid token")
        return _render_login(request, error=t(lang, "flash.auth.confirm_link_invalid"))
    logger.info("Email confirmed user_id=%s email=%s", user.id, user.email)
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
        logger.warning("Activation failed invalid token ip=%s", client_ip_key(request))
        return _render_login(
            request, error=t(lang, "flash.auth.activation_link_invalid")
        )
    set_user_session(request, user)
    logger.info(
        "Activation ok user_id=%s email=%s pending_was=%s",
        user.id,
        user.email,
        pending,
    )
    return RedirectResponse("/", status_code=303)


def _unsubscribe(db, token: str):
    parsed = parse_unsubscribe_token(token)
    if parsed is None:
        return None
    user = apply_unsubscribe(db, *parsed)
    if user is None:
        return None
    return user, parsed[1]


@router.get("/email/unsubscribe", response_class=HTMLResponse)
def email_unsubscribe_get(request: Request, db: DbSession, token: str = ""):
    lang = resolve_lang(request)
    result = _unsubscribe(db, token)
    if result is None:
        logger.warning("Unsubscribe invalid token ip=%s", client_ip_key(request))
        return render(
            request,
            "auth/unsubscribed.html",
            error=t(lang, "ui.auth.unsubscribe.invalid"),
        )
    user, pref = result
    logger.info("Unsubscribe ok user_id=%s pref=%s", user.id, pref)
    return render(
        request,
        "auth/unsubscribed.html",
        success=t(
            lang,
            "ui.auth.unsubscribe.done",
            type=t(lang, f"ui.profile.settings.{pref}"),
        ),
    )


@router.post("/email/unsubscribe")
def email_unsubscribe_post(request: Request, db: DbSession, token: str = ""):
    result = _unsubscribe(db, token)
    if result is None:
        logger.warning("Unsubscribe POST invalid token ip=%s", client_ip_key(request))
        return PlainTextResponse("Invalid token", status_code=400)
    user, pref = result
    logger.info("Unsubscribe one-click user_id=%s pref=%s", user.id, pref)
    return PlainTextResponse("OK", status_code=200)
