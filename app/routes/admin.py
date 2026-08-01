from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps.auth import AdminUser, DbSession
from app.models.enums import UserRole
from app.models.ticket import Tag
from app.models.user import Project, User
from app.rate_limit import limiter
from app.routes.context import render
from app.services import auth as auth_service
from app.services import projects as project_service
from app.utils.i18n import DEFAULT_LANG, resolve_lang, t
from app.utils.urls import admin_project_path

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_user_create_limit() -> str:
    return get_settings().auth_admin_user_create_rate_limit


def _admin_project(db: Session, key: str, *, lang: str | None = None) -> Project:
    return project_service.get_project_by_key_or_404(db, key, lang=lang)


def _form_truthy(value: str) -> bool:
    return value in ("1", "true", "on")


def _field_json_error(lang: str, exc: Exception) -> JSONResponse:
    msg = str(exc)
    field = None
    if msg in {
        t(lang, "messages.auth.email_required"),
        t(lang, "messages.auth.user_exists_resend"),
        t(lang, "messages.auth.email_taken"),
    }:
        field = "email"
    elif msg == t(lang, "messages.auth.name_required"):
        field = "first_name"
    if field:
        return JSONResponse(
            {"detail": {"field": field, "message": msg}}, status_code=400
        )
    return JSONResponse({"detail": msg}, status_code=400)


def _get_user_or_404(db: Session, user_id: int, *, lang: str | None = None) -> User:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(
            status_code=404, detail=t(lang or DEFAULT_LANG, "messages.http.not_found")
        )
    return target


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request, user: AdminUser, db: DbSession):
    return render(
        request,
        "admin/dashboard.html",
        user=user,
        projects=project_service.list_projects(db),
        users=project_service.list_users(db),
    )


@router.get("/projects", response_class=HTMLResponse)
def admin_projects(request: Request, user: AdminUser, db: DbSession):
    return render(
        request,
        "admin/projects.html",
        user=user,
        projects=project_service.list_project_summaries(db),
    )


@router.post("/projects")
def create_project(
    request: Request,
    user: AdminUser,
    db: DbSession,
    name: Annotated[str, Form()],
    key: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    try:
        project_service.create_project(db, name, key, description, lang=lang)
    except ValueError as exc:
        return render(
            request,
            "admin/projects.html",
            user=user,
            projects=project_service.list_project_summaries(db),
            error=str(exc),
            form_name=name,
            form_key=key,
            form_description=description,
        )
    return RedirectResponse("/admin/projects", status_code=303)


@router.post("/projects/{key}/active")
def admin_project_active(
    key: str,
    user: AdminUser,
    db: DbSession,
    active: Annotated[str, Form()],
):
    project = project_service.get_project_by_key(db, key)
    if project:
        project_service.set_project_active(db, project, active=_form_truthy(active))
    return RedirectResponse("/admin/projects", status_code=303)


def _project_detail_ctx(db: Session, project: Project) -> dict:
    return {
        "project": project,
        "members": project_service.list_project_member_users(
            db, project, include_admins=False
        ),
        "all_users": project_service.list_addable_users(db, project),
    }


@router.get("/projects/{key}", response_class=HTMLResponse)
def project_detail(request: Request, key: str, user: AdminUser, db: DbSession):
    project = _admin_project(db, key, lang=resolve_lang(request))
    return render(
        request,
        "admin/project_detail.html",
        user=user,
        **_project_detail_ctx(db, project),
    )


@router.post("/projects/{key}/edit")
def edit_project(
    request: Request,
    key: str,
    user: AdminUser,
    db: DbSession,
    name: Annotated[str, Form()],
    project_key: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    project = _admin_project(db, key, lang=lang)
    try:
        project = project_service.update_project(
            db, project, name=name, key=project_key, description=description, lang=lang
        )
    except ValueError as exc:
        return render(
            request,
            "admin/project_detail.html",
            user=user,
            error=str(exc),
            form_name=name,
            form_key=project_key,
            form_description=description,
            **_project_detail_ctx(db, project),
        )
    return RedirectResponse(admin_project_path(project), status_code=303)


@router.post("/projects/{key}/members")
def add_member(
    request: Request,
    key: str,
    user: AdminUser,
    db: DbSession,
    user_id: Annotated[int, Form()],
):
    project = _admin_project(db, key, lang=resolve_lang(request))
    project_service.add_project_member(db, project.id, user_id)
    return RedirectResponse(admin_project_path(project), status_code=303)


@router.post("/projects/{key}/members/{member_id}/remove")
def remove_member(
    request: Request,
    key: str,
    member_id: int,
    user: AdminUser,
    db: DbSession,
):
    project = _admin_project(db, key, lang=resolve_lang(request))
    project_service.remove_project_member(db, project.id, member_id)
    return RedirectResponse(admin_project_path(project), status_code=303)


@router.post("/projects/{key}/tags/{tag_id}/delete")
def delete_project_tag(
    key: str,
    tag_id: int,
    user: AdminUser,
    db: DbSession,
):
    project = _admin_project(db, key)
    tag = db.get(Tag, tag_id)
    if not tag or tag.project_id != project.id:
        raise HTTPException(status_code=404)
    db.delete(tag)
    db.commit()
    return RedirectResponse("/admin/projects", status_code=303)


_USER_OK_FLASH = {
    "created": "flash.admin.user_created",
    "updated": "flash.admin.user_updated",
    "password_link": "flash.admin.password_link_sent",
    "password_set": "flash.admin.password_set",
    "activation_resent": "flash.admin.activation_resent",
    "notifications": "flash.admin.notifications_updated",
}


def _users_redirect(*, ok: str | None = None) -> RedirectResponse:
    query = f"?ok={ok}" if ok else ""
    return RedirectResponse(f"/admin/users{query}", status_code=303)


def _user_edit_redirect(user_id: int, *, ok: str | None = None) -> RedirectResponse:
    query = f"?ok={ok}" if ok else ""
    return RedirectResponse(f"/admin/users/{user_id}{query}", status_code=303)


def _user_edit_ctx(db: Session, target: User, *, flash: str | None = None) -> dict:
    return {
        "edit_user": target,
        "projects": project_service.list_projects(db),
        "form_project_ids": [m.project_id for m in target.memberships],
        "is_admin_edit": True,
        "flash": flash,
    }


@router.get("/users", response_class=HTMLResponse)
def admin_users(
    request: Request,
    user: AdminUser,
    db: DbSession,
    role: str | None = None,
    project: str | None = None,
):
    lang = resolve_lang(request)
    ok = request.query_params.get("ok") or ""
    flash_key = _USER_OK_FLASH.get(ok)

    role_filter: UserRole | None = None
    filter_role = ""
    if role:
        try:
            role_filter = UserRole(role)
            filter_role = role_filter.value
        except ValueError:
            pass

    project_id: int | None = None
    filter_project = ""
    if project:
        try:
            pid = int(project)
        except ValueError:
            pid = None
        if pid is not None and db.get(Project, pid) is not None:
            project_id = pid
            filter_project = str(pid)

    return render(
        request,
        "admin/users.html",
        user=user,
        users=project_service.list_users(db, role=role_filter, project_id=project_id),
        projects=project_service.list_projects(db),
        form_project_ids=[],
        filter_role=filter_role,
        filter_project=filter_project,
        flash=t(lang, flash_key) if flash_key else None,
    )


@router.post("/users/new")
@limiter.limit(_admin_user_create_limit)
async def admin_user_create(
    request: Request,
    user: AdminUser,
    db: DbSession,
):
    lang = resolve_lang(request)
    form = await request.form()
    first_name = str(form.get("first_name") or "")
    last_name = str(form.get("last_name") or "")
    email = str(form.get("email") or "")
    role_raw = str(form.get("role") or UserRole.USER.value)
    raw_ids = form.getlist("project_ids")
    project_ids = [int(str(x)) for x in raw_ids if x]

    try:
        role = UserRole(role_raw)
    except ValueError:
        return JSONResponse(
            {"detail": t(lang, "messages.admin.invalid_role")}, status_code=400
        )
    try:
        target = auth_service.create_pending_user(
            db,
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
            project_ids=project_ids,
            lang=lang,
        )
        auth_service.send_password_link(db, target, lang=lang)
    except ValueError as exc:
        db.rollback()
        return _field_json_error(lang, exc)
    return _user_edit_redirect(target.id, ok="created")


@router.get("/users/{user_id}", response_class=HTMLResponse)
def admin_user_edit(request: Request, user_id: int, user: AdminUser, db: DbSession):
    lang = resolve_lang(request)
    target = _get_user_or_404(db, user_id, lang=lang)
    ok = request.query_params.get("ok") or ""
    flash_key = _USER_OK_FLASH.get(ok)
    return render(
        request,
        "admin/user_edit.html",
        user=user,
        **_user_edit_ctx(db, target, flash=t(lang, flash_key) if flash_key else None),
    )


@router.post("/users/{user_id}")
async def admin_user_update(
    request: Request,
    user_id: int,
    user: AdminUser,
    db: DbSession,
):
    lang = resolve_lang(request)
    target = _get_user_or_404(db, user_id, lang=lang)
    form = await request.form()
    first_name = str(form.get("first_name") or "")
    last_name = str(form.get("last_name") or "")
    email = str(form.get("email") or "")
    phone = str(form.get("phone") or "")
    role_raw = str(form.get("role") or "")
    project_ids = [int(str(x)) for x in form.getlist("project_ids") if x]
    try:
        auth_service.update_profile_fields(
            db,
            target,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            lang=lang,
        )
        auth_service.admin_set_email(db, target, email, lang=lang)
        if role_raw and target.id != user.id:
            try:
                new_role = UserRole(role_raw)
            except ValueError:
                raise ValueError(t(lang, "messages.admin.invalid_role")) from None
            if new_role != target.role:
                auth_service.set_user_role(db, target, new_role, lang=lang)
        project_service.set_user_projects(db, target.id, project_ids, lang=lang)
        db.commit()
        db.refresh(target)
    except ValueError as exc:
        db.rollback()
        return _field_json_error(lang, exc)
    return _user_edit_redirect(user_id, ok="updated")


@router.post("/users/{user_id}/active")
def admin_user_active(
    request: Request,
    user_id: int,
    user: AdminUser,
    db: DbSession,
    active: Annotated[str, Form()],
    return_to: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    target = db.get(User, user_id)
    if target:
        try:
            auth_service.set_active(
                db,
                target,
                actor=user,
                active=_form_truthy(active),
                lang=lang,
            )
        except ValueError:
            pass
    if return_to == "edit":
        return _user_edit_redirect(user_id)
    return _users_redirect()


@router.post("/users/{user_id}/password")
def admin_user_password(
    request: Request,
    user_id: int,
    user: AdminUser,
    db: DbSession,
    action: Annotated[str, Form()],
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    target = _get_user_or_404(db, user_id, lang=lang)
    try:
        if action == "send_link":
            if not auth_service.can_receive_password_link(target):
                raise ValueError(t(lang, "flash.auth.account_blocked"))
            auth_service.send_password_link(db, target, lang=lang)
            ok = "password_link"
        elif action == "set":
            auth_service.require_matching_passwords(
                new_password, confirm_password, lang=lang
            )
            auth_service.admin_set_password(db, target, new_password, lang=lang)
            ok = "password_set"
        else:
            raise ValueError(t(lang, "messages.admin.unknown_action"))
    except ValueError as exc:
        db.rollback()
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return _user_edit_redirect(user_id, ok=ok)


@router.post("/users/{user_id}/notifications")
def admin_user_notifications(
    request: Request,
    user_id: int,
    user: AdminUser,
    db: DbSession,
    notify_new_ticket: Annotated[str, Form()] = "",
    notify_reply: Annotated[str, Form()] = "",
    notify_ticket_update: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    target = _get_user_or_404(db, user_id, lang=lang)
    auth_service.update_notification_prefs(
        db,
        target,
        notify_new_ticket=bool(notify_new_ticket),
        notify_reply=bool(notify_reply),
        notify_ticket_update=bool(notify_ticket_update),
    )
    return _user_edit_redirect(user_id, ok="notifications")


@router.post("/users/{user_id}/resend-activation")
@limiter.limit(_admin_user_create_limit)
def admin_user_resend_activation(
    request: Request,
    user_id: int,
    user: AdminUser,
    db: DbSession,
    return_to: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    target = _get_user_or_404(db, user_id, lang=lang)
    try:
        if not target.is_pending:
            raise ValueError(t(lang, "messages.admin.already_activated"))
        if not auth_service.can_receive_password_link(target):
            raise ValueError(t(lang, "flash.auth.account_blocked"))
        auth_service.send_password_link(db, target, lang=lang)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    if return_to == "edit":
        return _user_edit_redirect(user_id, ok="activation_resent")
    return _users_redirect(ok="activation_resent")
