from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps.auth import AdminUser, DbSession
from app.models.enums import UserRole
from app.models.user import Project, User
from app.rate_limit import limiter
from app.routes.context import render
from app.services import auth as auth_service
from app.services import projects as project_service
from app.utils.urls import admin_project_path

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_user_create_limit() -> str:
    return get_settings().auth_admin_user_create_rate_limit


def _admin_project(db: Session, key: str) -> Project:
    return project_service.get_project_by_key_or_404(db, key)


def _get_user_or_404(db: Session, user_id: int) -> User:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Nie znaleziono")
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
    try:
        project_service.create_project(db, name, key, description)
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


@router.post("/projects/{key}/delete")
def delete_project(key: str, user: AdminUser, db: DbSession):
    project = project_service.get_project_by_key(db, key)
    if project:
        project_service.delete_project(db, project)
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
    project = _admin_project(db, key)
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
    project = _admin_project(db, key)
    try:
        project = project_service.update_project(
            db, project, name=name, key=project_key, description=description
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
    key: str,
    user: AdminUser,
    db: DbSession,
    user_id: Annotated[int, Form()],
):
    project = _admin_project(db, key)
    project_service.add_project_member(db, project.id, user_id)
    return RedirectResponse(admin_project_path(project), status_code=303)


@router.post("/projects/{key}/members/{member_id}/remove")
def remove_member(
    key: str,
    member_id: int,
    user: AdminUser,
    db: DbSession,
):
    project = _admin_project(db, key)
    project_service.remove_project_member(db, project.id, member_id)
    return RedirectResponse(admin_project_path(project), status_code=303)


@router.get("/users", response_class=HTMLResponse)
def admin_users(request: Request, user: AdminUser, db: DbSession):
    return render(
        request, "admin/users.html", user=user, users=project_service.list_users(db)
    )


def _render_user_edit(
    request: Request,
    *,
    db: Session,
    user: User,
    edit_user: User,
    error: str | None = None,
    success: str | None = None,
    form_project_ids: list[int] | None = None,
):
    if form_project_ids is None:
        form_project_ids = [m.project_id for m in edit_user.memberships]
    return render(
        request,
        "admin/user_edit.html",
        user=user,
        edit_user=edit_user,
        is_admin_edit=True,
        form_action=f"/admin/users/{edit_user.id}",
        projects=project_service.list_projects(db),
        form_project_ids=form_project_ids,
        error=error,
        success=success,
    )


@router.get("/users/new", response_class=HTMLResponse)
def admin_user_new_page(request: Request, user: AdminUser, db: DbSession):
    return render(
        request,
        "admin/user_new.html",
        user=user,
        projects=project_service.list_projects(db),
        error=None,
        form_first_name="",
        form_last_name="",
        form_email="",
        form_role=UserRole.USER.value,
        form_project_ids=[],
    )


@router.post("/users/new")
@limiter.limit(_admin_user_create_limit)
async def admin_user_create(
    request: Request,
    background_tasks: BackgroundTasks,
    user: AdminUser,
    db: DbSession,
):
    form = await request.form()
    first_name = str(form.get("first_name") or "")
    last_name = str(form.get("last_name") or "")
    email = str(form.get("email") or "")
    role_raw = str(form.get("role") or UserRole.USER.value)
    raw_ids = form.getlist("project_ids")
    project_ids = [int(str(x)) for x in raw_ids if x]

    def _error(msg: str):
        return render(
            request,
            "admin/user_new.html",
            user=user,
            projects=project_service.list_projects(db),
            error=msg,
            form_first_name=first_name,
            form_last_name=last_name,
            form_email=email,
            form_role=role_raw,
            form_project_ids=project_ids,
        )

    try:
        role = UserRole(role_raw)
    except ValueError:
        return _error("Nieprawidłowa rola.")
    try:
        target = auth_service.create_pending_user(
            db,
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
            project_ids=project_ids,
        )
        auth_service.send_password_link(db, background_tasks, target)
    except ValueError as exc:
        db.rollback()
        return _error(str(exc))
    return RedirectResponse(f"/admin/users/{target.id}?created=1", status_code=303)


@router.get("/users/{user_id}", response_class=HTMLResponse)
def admin_user_edit(request: Request, user_id: int, user: AdminUser, db: DbSession):
    target = _get_user_or_404(db, user_id)
    success = None
    if request.query_params.get("created"):
        success = "Użytkownik utworzony. Wysłano link aktywacyjny."
    return _render_user_edit(
        request, db=db, user=user, edit_user=target, success=success
    )


@router.post("/users/{user_id}")
async def admin_user_update(
    request: Request,
    user_id: int,
    user: AdminUser,
    db: DbSession,
):
    target = _get_user_or_404(db, user_id)
    form = await request.form()
    first_name = str(form.get("first_name") or "")
    last_name = str(form.get("last_name") or "")
    email = str(form.get("email") or "")
    phone = str(form.get("phone") or "")
    project_ids = [int(str(x)) for x in form.getlist("project_ids") if x]
    try:
        auth_service.update_profile_fields(
            db, target, first_name=first_name, last_name=last_name, phone=phone
        )
        auth_service.admin_set_email(db, target, email)
        project_service.set_user_projects(db, target.id, project_ids)
        db.commit()
        db.refresh(target)
    except ValueError as exc:
        db.rollback()
        target = db.get(User, user_id) or target
        return _render_user_edit(
            request,
            db=db,
            user=user,
            edit_user=target,
            error=str(exc),
            form_project_ids=project_ids,
        )
    return _render_user_edit(
        request,
        db=db,
        user=user,
        edit_user=target,
        success="Użytkownik został zaktualizowany.",
    )


@router.post("/users/{user_id}/active")
def admin_user_active(
    user_id: int,
    user: AdminUser,
    db: DbSession,
    active: Annotated[str, Form()],
):
    target = db.get(User, user_id)
    if target:
        try:
            auth_service.set_active(
                db, target, actor=user, active=active in ("1", "true", "on")
            )
        except ValueError:
            pass
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/password")
def admin_user_password(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: int,
    user: AdminUser,
    db: DbSession,
    action: Annotated[str, Form()],
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
):
    target = _get_user_or_404(db, user_id)
    try:
        if action == "send_link":
            if not auth_service.can_receive_password_link(target):
                raise ValueError("Konto jest zablokowane.")
            auth_service.send_password_link(db, background_tasks, target)
            success = "Wysłano e-mail z linkiem do ustawienia hasła."
        elif action == "set":
            auth_service.require_matching_passwords(new_password, confirm_password)
            auth_service.admin_set_password(db, target, new_password)
            success = "Hasło zostało ustawione."
        else:
            raise ValueError("Nieznana akcja.")
    except ValueError as exc:
        db.rollback()
        target = db.get(User, user_id) or target
        return _render_user_edit(
            request, db=db, user=user, edit_user=target, error=str(exc)
        )
    return _render_user_edit(
        request, db=db, user=user, edit_user=target, success=success
    )


@router.post("/users/{user_id}/resend-activation")
@limiter.limit(_admin_user_create_limit)
def admin_user_resend_activation(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: int,
    user: AdminUser,
    db: DbSession,
):
    target = _get_user_or_404(db, user_id)
    try:
        if not target.is_pending:
            raise ValueError("Konto jest już aktywowane.")
        if not auth_service.can_receive_password_link(target):
            raise ValueError("Konto jest zablokowane.")
        auth_service.send_password_link(db, background_tasks, target)
    except ValueError as exc:
        return _render_user_edit(
            request, db=db, user=user, edit_user=target, error=str(exc)
        )
    return _render_user_edit(
        request,
        db=db,
        user=user,
        edit_user=target,
        success="Wysłano ponownie link aktywacyjny.",
    )


@router.post("/users/{user_id}/role")
def set_role(
    user_id: int,
    user: AdminUser,
    db: DbSession,
    role: Annotated[str, Form()],
):
    target = db.get(User, user_id)
    if target and target.id != user.id:
        try:
            auth_service.set_user_role(db, target, UserRole(role))
        except ValueError:
            pass
    return RedirectResponse("/admin/users", status_code=303)
