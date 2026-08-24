from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps.auth import AdminUser, DbSession, get_last_project_key
from app.models.enums import UserRole
from app.models.ticket import Tag
from app.models.user import Project, User
from app.rate_limit import limiter
from app.routes import admin_settings
from app.routes.context import render
from app.services import auth as auth_service
from app.services import projects as project_service
from app.utils.i18n import DEFAULT_LANG, normalize_lang, resolve_lang, t
from app.utils.urls import admin_project_path

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(admin_settings.router)


def _admin_user_create_limit() -> str:
    return get_settings().auth_admin_user_create_rate_limit


_USER_SORT_COLS = ("name", "email", "phone", "role", "status")
_ACTIVITY_SORT_COLS = ("name", "role", "tickets", "last_login")
_MEMBER_SORT_COLS = ("name", "role")
_USER_STATUS_FILTERS = ("active", "blocked", "pending")


def _admin_path(base: str, **params: str) -> str:
    clean: dict[str, str] = {}
    for key, value in params.items():
        if not value:
            continue
        if key == "sort" and value == "name":
            continue
        if key == "order" and value == "asc":
            continue
        clean[key] = value
    qs = urlencode(clean)
    return f"{base}?{qs}" if qs else base


def _parse_sort(
    sort: str | None,
    order: str | None,
    *,
    allowed: tuple[str, ...],
) -> tuple[str, str]:
    col = (sort or "").strip().lower()
    if col not in allowed:
        col = allowed[0]
    direction = "desc" if (order or "").strip().lower() == "desc" else "asc"
    return col, direction


def _sort_links(
    base: str,
    cols: tuple[str, ...],
    *,
    sort: str,
    order: str,
    **filters: str,
) -> dict[str, str]:
    return {
        col: _admin_path(
            base,
            sort=col,
            order=("desc" if col == sort and order == "asc" else "asc"),
            **filters,
        )
        for col in cols
    }


def _parse_user_status(status: str | None) -> str:
    raw = (status or "").strip().lower()
    return raw if raw in _USER_STATUS_FILTERS else ""


def _admin_project(db: Session, key: str, *, lang: str | None = None) -> Project:
    return project_service.get_project_by_key_or_404(db, key, lang=lang)


def _form_truthy(value: str) -> bool:
    return value in ("1", "true", "on")


def _admin_projects_path(*, disabled: bool = False) -> str:
    return "/admin/projects?disabled=1" if disabled else "/admin/projects"


def _admin_projects_ctx(db: Session, *, show_disabled: bool, **extra) -> dict:
    return {
        "show_disabled": show_disabled,
        "projects": project_service.list_project_summaries(
            db, disabled_only=show_disabled
        ),
        "staff_candidates": project_service.list_staff_candidates(db),
        **extra,
    }


def _form_text(form, key: str) -> str:
    return str(form.get(key) or "")


def _parse_role(raw: str, *, lang: str) -> UserRole:
    try:
        return UserRole(raw)
    except ValueError:
        raise ValueError(t(lang, "messages.admin.invalid_role")) from None


def _field_json_error(lang: str, exc: Exception) -> JSONResponse:
    from app.validation import ValidationValueError

    msg = str(exc)
    field = None
    if isinstance(exc, ValidationValueError):
        field = exc.field.rsplit(".", 1)[-1]
    elif msg in {
        t(lang, "messages.auth.user_exists_resend"),
        t(lang, "messages.auth.email_taken"),
    }:
        field = "email"
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
def admin_home(
    request: Request,
    user: AdminUser,
    db: DbSession,
    project: Annotated[str, Query()] = "",
    sort: Annotated[str, Query()] = "",
    order: Annotated[str, Query()] = "",
):
    projects = project_service.list_projects(db, active_only=True)
    selected_project = None
    project_stats = None
    project_activity = []
    sort_col, sort_dir = _parse_sort(sort, order, allowed=_ACTIVITY_SORT_COLS)
    if projects:
        raw = (project or "").strip()
        if raw.isdigit():
            selected_project = next((p for p in projects if p.id == int(raw)), None)
        if selected_project is None:
            last_key = get_last_project_key(request)
            selected_project = next(
                (p for p in projects if p.key == last_key), projects[0]
            )
        result = project_service.admin_project_stats(
            db,
            selected_project.id,
            sort=sort_col,
            sort_dir=sort_dir,
        )
        if result is not None:
            project_stats, project_activity = result
    return render(
        request,
        "admin/dashboard.html",
        user=user,
        stats=project_service.admin_dashboard_stats(db),
        projects=projects,
        selected_project=selected_project,
        project_stats=project_stats,
        project_activity=project_activity,
        activity_sort=sort_col,
        activity_sort_dir=sort_dir,
        activity_sort_links=_sort_links(
            "/admin",
            _ACTIVITY_SORT_COLS,
            sort=sort_col,
            order=sort_dir,
            project=str(selected_project.id) if selected_project else "",
        ),
    )


@router.get("/projects", response_class=HTMLResponse)
def admin_projects(
    request: Request,
    user: AdminUser,
    db: DbSession,
    disabled: Annotated[str, Query()] = "",
):
    show_disabled = _form_truthy(disabled)
    return render(
        request,
        "admin/projects.html",
        user=user,
        **_admin_projects_ctx(db, show_disabled=show_disabled),
    )


@router.post("/projects")
def create_project(
    request: Request,
    user: AdminUser,
    db: DbSession,
    name: Annotated[str, Form()],
    key: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    staff_user_id: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    show_disabled = _form_truthy(request.query_params.get("disabled", ""))
    staff_ids = [int(staff_user_id)] if staff_user_id.strip().isdigit() else []
    try:
        project_service.create_project(
            db,
            name,
            key,
            description,
            initial_staff_ids=staff_ids,
            lang=lang,
        )
    except ValueError as exc:
        return render(
            request,
            "admin/projects.html",
            user=user,
            **_admin_projects_ctx(
                db,
                show_disabled=show_disabled,
                error=str(exc),
                form_name=name,
                form_key=key,
                form_description=description,
                form_staff_user_id=staff_user_id,
            ),
        )
    return RedirectResponse(_admin_projects_path(), status_code=303)


@router.post("/projects/{key}/active")
def admin_project_active(
    key: str,
    user: AdminUser,
    db: DbSession,
    active: Annotated[str, Form()],
    disabled: Annotated[str, Form()] = "",
):
    project = project_service.get_project_by_key(db, key)
    if project:
        project_service.set_project_active(db, project, active=_form_truthy(active))
    return RedirectResponse(
        _admin_projects_path(disabled=_form_truthy(disabled)), status_code=303
    )


def _project_detail_ctx(
    db: Session,
    project: Project,
    *,
    sort: str = "name",
    sort_dir: str = "asc",
) -> dict:
    return {
        "project": project,
        "members": project_service.list_project_member_users(
            db, project, sort=sort, sort_dir=sort_dir
        ),
        "all_users": project_service.list_addable_users(db, project),
        "sort": sort,
        "sort_dir": sort_dir,
        "sort_links": _sort_links(
            admin_project_path(project),
            _MEMBER_SORT_COLS,
            sort=sort,
            order=sort_dir,
        ),
    }


@router.get("/projects/{key}", response_class=HTMLResponse)
def project_detail(
    request: Request,
    key: str,
    user: AdminUser,
    db: DbSession,
    sort: Annotated[str, Query()] = "",
    order: Annotated[str, Query()] = "",
):
    project = _admin_project(db, key, lang=resolve_lang(request))
    sort_col, sort_dir = _parse_sort(sort, order, allowed=_MEMBER_SORT_COLS)
    return render(
        request,
        "admin/project_detail.html",
        user=user,
        **_project_detail_ctx(db, project, sort=sort_col, sort_dir=sort_dir),
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
            db,
            project,
            name=name,
            key=project_key,
            description=description,
            lang=lang,
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


@router.post("/projects/{key}/notifications")
def project_notifications(
    request: Request,
    key: str,
    user: AdminUser,
    db: DbSession,
    notify_clients_on_staff_ticket: Annotated[str, Form()] = "",
):
    project = _admin_project(db, key, lang=resolve_lang(request))
    project_service.set_project_notify_clients_on_staff_ticket(
        db, project, enabled=bool(notify_clients_on_staff_ticket)
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
    lang = resolve_lang(request)
    project = _admin_project(db, key, lang=lang)
    try:
        project_service.remove_project_member(db, project.id, member_id, lang=lang)
    except ValueError as exc:
        return render(
            request,
            "admin/project_detail.html",
            user=user,
            error=str(exc),
            **_project_detail_ctx(db, project),
        )
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
    "created_active": "flash.admin.user_created_active",
    "updated": "flash.admin.user_updated",
    "password_link": "flash.admin.password_link_sent",
    "password_set": "flash.admin.password_set",
    "activation_resent": "flash.admin.activation_resent",
    "notifications": "flash.admin.notifications_updated",
    "blocked": "flash.admin.user_blocked",
    "unblocked": "flash.admin.user_unblocked",
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
        "projects": project_service.list_projects(db, active_only=True),
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
    q: str | None = None,
    status: str | None = None,
    sort: str | None = None,
    order: str | None = None,
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

    filter_q = (q or "").strip()
    filter_status = _parse_user_status(status)
    sort_col, sort_dir = _parse_sort(sort, order, allowed=_USER_SORT_COLS)

    error = None
    try:
        users = project_service.list_users(
            db,
            role=role_filter,
            project_id=project_id,
            q=filter_q or None,
            status=filter_status or None,
            sort=sort_col,
            sort_dir=sort_dir,
            lang=lang,
        )
    except ValueError as exc:
        users = []
        error = str(exc)

    return render(
        request,
        "admin/users.html",
        user=user,
        users=users,
        projects=project_service.list_projects(db),
        form_projects=project_service.list_projects(db, active_only=True),
        form_project_ids=[],
        filter_role=filter_role,
        filter_project=filter_project,
        filter_q=filter_q,
        filter_status=filter_status,
        status_choices=tuple(
            {
                "value": key,
                "label": t(lang, f"ui.admin.users.filter_status_{key}"),
            }
            for key in _USER_STATUS_FILTERS
        ),
        sort=sort_col,
        sort_dir=sort_dir,
        sort_links=_sort_links(
            "/admin/users",
            _USER_SORT_COLS,
            sort=sort_col,
            order=sort_dir,
            q=filter_q,
            role=filter_role,
            project=filter_project,
            status=filter_status,
        ),
        error=error,
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
    activate = _form_text(form, "mode") == "active"
    try:
        target = auth_service.create_user(
            db,
            first_name=_form_text(form, "first_name"),
            last_name=_form_text(form, "last_name"),
            email=_form_text(form, "email"),
            phone=_form_text(form, "phone"),
            role=_parse_role(
                _form_text(form, "role") or UserRole.USER.value, lang=lang
            ),
            project_ids=[int(str(x)) for x in form.getlist("project_ids") if x],
            lang=lang,
            ui_lang=normalize_lang(_form_text(form, "ui_lang")),
            activate=activate,
        )
        if not activate:
            auth_service.send_password_link(db, target, lang=lang)
    except ValueError as exc:
        db.rollback()
        return _field_json_error(lang, exc)
    return _user_edit_redirect(
        target.id, ok="created_active" if activate else "created"
    )


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
    try:
        auth_service.update_profile_fields(
            db,
            target,
            first_name=_form_text(form, "first_name"),
            last_name=_form_text(form, "last_name"),
            phone=_form_text(form, "phone"),
            lang=lang,
        )
        auth_service.admin_set_email(db, target, _form_text(form, "email"), lang=lang)
        target.ui_lang = normalize_lang(_form_text(form, "ui_lang"))
        role_raw = _form_text(form, "role")
        if role_raw and target.id != user.id:
            new_role = _parse_role(role_raw, lang=lang)
            if new_role != target.role:
                auth_service.set_user_role(db, target, new_role, lang=lang)
        project_service.set_user_projects(
            db,
            target.id,
            [int(str(x)) for x in form.getlist("project_ids") if x],
            lang=lang,
        )
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
    target = _get_user_or_404(db, user_id, lang=lang)
    want_active = _form_truthy(active)
    try:
        auth_service.set_active(
            db,
            target,
            actor=user,
            active=want_active,
            lang=lang,
        )
    except ValueError as exc:
        if return_to == "edit":
            return render(
                request,
                "admin/user_edit.html",
                user=user,
                **_user_edit_ctx(db, target, flash=None),
                error=str(exc),
            )
        return _users_redirect()
    if return_to == "edit":
        return _user_edit_redirect(
            user_id, ok="unblocked" if want_active else "blocked"
        )
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
