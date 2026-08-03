from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.deps.auth import AdminUser, DbSession
from app.routes.context import render
from app.services import portal_settings as portal_settings_service
from app.services.email import send_smtp_test
from app.utils.i18n import resolve_lang, t

router = APIRouter(prefix="/settings")

_FLASH_OK = {
    "saved": "flash.admin.settings_saved",
    "test_sent": "flash.admin.settings_test_sent",
}
_FLASH_ERR = {
    "test_failed": "flash.admin.settings_test_failed",
    "smtp_missing": "flash.admin.settings_smtp_missing",
}


def _flash(request: Request, lang: str) -> tuple[str | None, str | None]:
    ok = (request.query_params.get("ok") or "").strip()
    if ok in _FLASH_OK:
        return t(lang, _FLASH_OK[ok]), None
    if ok in _FLASH_ERR:
        return None, t(lang, _FLASH_ERR[ok])
    return None, None


def _path(section: str, **params: str) -> str:
    qs = urlencode({k: v for k, v in params.items() if v})
    base = f"/admin/settings/{section}"
    return f"{base}?{qs}" if qs else base


def _uploads_form(db: Session) -> dict:
    vals = portal_settings_service.form_values_for_section("uploads", db)
    return {
        "upload_max_files": vals["upload_max_files"],
        "upload_max_image_mb": round(vals["upload_max_image_bytes"] / (1024 * 1024), 2),
        "upload_max_file_mb": round(vals["upload_max_file_bytes"] / (1024 * 1024), 2),
    }


def _page(
    request: Request,
    user: AdminUser,
    db: DbSession,
    *,
    section: str,
    template: str,
    form: dict,
    test_email: str | None = None,
    error: str | None = None,
):
    lang = resolve_lang(request)
    flash, flash_error = _flash(request, lang)
    ctx = {
        "user": user,
        "settings_section": section,
        "form": form,
        "flash": flash,
        "error": error or flash_error,
    }
    if test_email is not None:
        ctx["test_email"] = test_email
    return render(request, template, **ctx)


@router.get("", response_class=HTMLResponse)
def admin_settings_home():
    return RedirectResponse("/admin/settings/tickets", status_code=303)


@router.get("/tickets", response_class=HTMLResponse)
def admin_settings_tickets(request: Request, user: AdminUser, db: DbSession):
    return _page(
        request,
        user,
        db,
        section="tickets",
        template="admin/settings_tickets.html",
        form=portal_settings_service.form_values_for_section("tickets", db),
    )


@router.post("/tickets")
def admin_settings_tickets_save(
    request: Request,
    user: AdminUser,
    db: DbSession,
    ticket_reopen_days: Annotated[str, Form()],
    auth_link_ttl_days: Annotated[str, Form()],
    email_confirm_ttl_minutes: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    form = {
        "ticket_reopen_days": ticket_reopen_days,
        "auth_link_ttl_days": auth_link_ttl_days,
        "email_confirm_ttl_minutes": email_confirm_ttl_minutes,
    }
    try:
        portal_settings_service.update_section(db, "tickets", form, lang=lang)
    except ValueError as exc:
        return _page(
            request,
            user,
            db,
            section="tickets",
            template="admin/settings_tickets.html",
            form=form,
            error=str(exc),
        )
    return RedirectResponse(_path("tickets", ok="saved"), status_code=303)


@router.get("/uploads", response_class=HTMLResponse)
def admin_settings_uploads(request: Request, user: AdminUser, db: DbSession):
    return _page(
        request,
        user,
        db,
        section="uploads",
        template="admin/settings_uploads.html",
        form=_uploads_form(db),
    )


@router.post("/uploads")
def admin_settings_uploads_save(
    request: Request,
    user: AdminUser,
    db: DbSession,
    upload_max_files: Annotated[str, Form()],
    upload_max_image_mb: Annotated[str, Form()],
    upload_max_file_mb: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    form = {
        "upload_max_files": upload_max_files,
        "upload_max_image_mb": upload_max_image_mb,
        "upload_max_file_mb": upload_max_file_mb,
    }
    try:
        try:
            image_mb = float(str(upload_max_image_mb).strip().replace(",", "."))
            file_mb = float(str(upload_max_file_mb).strip().replace(",", "."))
        except ValueError as exc:
            raise ValueError(t(lang, "messages.admin.settings_invalid_int")) from exc
        if image_mb <= 0 or file_mb <= 0:
            raise ValueError(t(lang, "messages.admin.settings_out_of_range"))
        portal_settings_service.update_section(
            db,
            "uploads",
            {
                "upload_max_files": upload_max_files,
                "upload_max_image_bytes": round(image_mb * 1024 * 1024),
                "upload_max_file_bytes": round(file_mb * 1024 * 1024),
            },
            lang=lang,
        )
    except ValueError as exc:
        return _page(
            request,
            user,
            db,
            section="uploads",
            template="admin/settings_uploads.html",
            form=form,
            error=str(exc),
        )
    return RedirectResponse(_path("uploads", ok="saved"), status_code=303)


@router.get("/mail", response_class=HTMLResponse)
def admin_settings_mail(request: Request, user: AdminUser, db: DbSession):
    test_email = (request.query_params.get("test_email") or user.email or "").strip()
    return _page(
        request,
        user,
        db,
        section="mail",
        template="admin/settings_mail.html",
        form=portal_settings_service.form_values_for_section("mail", db),
        test_email=test_email,
    )


@router.post("/mail")
def admin_settings_mail_save(
    request: Request,
    user: AdminUser,
    db: DbSession,
    smtp_server: Annotated[str, Form()] = "",
    smtp_port: Annotated[str, Form()] = "587",
    smtp_security: Annotated[str, Form()] = "starttls",
    smtp_user: Annotated[str, Form()] = "",
    smtp_pass: Annotated[str, Form()] = "",
    email_from: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    values = {
        "smtp_server": smtp_server,
        "smtp_port": smtp_port,
        "smtp_security": smtp_security,
        "smtp_user": smtp_user,
        "smtp_pass": smtp_pass,
        "email_from": email_from,
    }
    try:
        portal_settings_service.update_section(db, "mail", values, lang=lang)
    except ValueError as exc:
        form = portal_settings_service.form_values_for_section("mail", db)
        form.update({k: v for k, v in values.items() if k != "smtp_pass"})
        return _page(
            request,
            user,
            db,
            section="mail",
            template="admin/settings_mail.html",
            form=form,
            test_email=user.email or "",
            error=str(exc),
        )
    return RedirectResponse(_path("mail", ok="saved"), status_code=303)


@router.post("/mail/test")
def admin_settings_mail_test(
    request: Request,
    user: AdminUser,
    db: DbSession,
    test_email: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    to_addr = (test_email or user.email or "").strip()
    if not to_addr:
        return RedirectResponse(_path("mail", ok="test_failed"), status_code=303)
    ps = portal_settings_service.get_portal_settings(db)
    if not ps.smtp_configured:
        return RedirectResponse(
            _path("mail", ok="smtp_missing", test_email=to_addr),
            status_code=303,
        )
    ok = send_smtp_test(to_email=to_addr, lang=lang, db=db)
    return RedirectResponse(
        _path("mail", ok="test_sent" if ok else "test_failed", test_email=to_addr),
        status_code=303,
    )
