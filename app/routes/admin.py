from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps.auth import AdminUser, DbSession
from app.models.enums import UserRole
from app.models.ticket import InviteLink
from app.models.user import Project, User
from app.routes.context import render
from app.services import auth as auth_service
from app.services import projects as project_service
from app.services.email import notify_password_set
from app.utils.urls import admin_project_path

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_project(db: Session, key: str) -> Project:
    project = project_service.get_project_by_key(db, key)
    if not project:
        raise HTTPException(status_code=404, detail="Nie znaleziono")
    return project


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request, user: AdminUser, db: DbSession):
    return render(
        request,
        "admin/dashboard.html",
        user=user,
        projects=project_service.list_projects(db),
        users=project_service.list_users(db),
        invites=project_service.list_invites(db),
    )


@router.get("/projects", response_class=HTMLResponse)
def admin_projects(request: Request, user: AdminUser, db: DbSession):
    return render(
        request,
        "admin/projects.html",
        user=user,
        projects=project_service.list_projects(db),
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
        project = project_service.create_project(db, name, key, description)
    except ValueError as exc:
        return render(
            request,
            "admin/projects.html",
            user=user,
            projects=project_service.list_projects(db),
            error=str(exc),
            form_name=name,
            form_key=key,
            form_description=description,
        )
    project_service.add_project_member(db, project.id, user.id)
    return RedirectResponse("/admin/projects", status_code=303)


@router.post("/projects/{key}/delete")
def delete_project(key: str, user: AdminUser, db: DbSession):
    project = project_service.get_project_by_key(db, key)
    if project:
        project_service.delete_project(db, project)
    return RedirectResponse("/admin/projects", status_code=303)


@router.get("/projects/{key}", response_class=HTMLResponse)
def project_detail(request: Request, key: str, user: AdminUser, db: DbSession):
    project = _admin_project(db, key)
    return render(
        request,
        "admin/project_detail.html",
        user=user,
        project=project,
        members=project.members,
        all_users=project_service.list_users(db),
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
            project=project,
            members=project.members,
            all_users=project_service.list_users(db),
            error=str(exc),
            form_name=name,
            form_key=project_key,
            form_description=description,
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
    user: User,
    edit_user: User,
    error: str | None = None,
    success: str | None = None,
):
    return render(
        request,
        "admin/user_edit.html",
        user=user,
        edit_user=edit_user,
        is_admin_edit=True,
        form_action=f"/admin/users/{edit_user.id}",
        error=error,
        success=success,
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
def admin_user_edit(request: Request, user_id: int, user: AdminUser, db: DbSession):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Nie znaleziono")
    return _render_user_edit(request, user=user, edit_user=target)


@router.post("/users/{user_id}")
def admin_user_update(
    request: Request,
    user_id: int,
    user: AdminUser,
    db: DbSession,
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    phone: Annotated[str, Form()] = "",
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Nie znaleziono")
    try:
        auth_service.update_profile_fields(
            db, target, first_name=first_name, last_name=last_name, phone=phone
        )
        auth_service.admin_set_email(db, target, email)
        db.commit()
        db.refresh(target)
    except ValueError as exc:
        db.rollback()
        target = db.get(User, user_id) or target
        return _render_user_edit(request, user=user, edit_user=target, error=str(exc))
    return _render_user_edit(
        request,
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
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Nie znaleziono")
    try:
        if action == "send_link":
            token_row = auth_service.send_password_set_token(db, target)
            notify_password_set(background_tasks, target, token_row.token)
            success = "Wysłano e-mail z linkiem do ustawienia hasła."
        elif action == "set":
            if new_password != confirm_password:
                raise ValueError("Hasła nie są zgodne.")
            auth_service.admin_set_password(db, target, new_password)
            success = "Hasło zostało ustawione."
        else:
            raise ValueError("Nieznana akcja.")
    except ValueError as exc:
        db.rollback()
        target = db.get(User, user_id) or target
        return _render_user_edit(request, user=user, edit_user=target, error=str(exc))
    return _render_user_edit(request, user=user, edit_user=target, success=success)


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


@router.get("/invites", response_class=HTMLResponse)
def admin_invites(request: Request, user: AdminUser, db: DbSession):
    settings = get_settings()
    return render(
        request,
        "admin/invites.html",
        user=user,
        invites=project_service.list_invites(db),
        projects=project_service.list_projects(db),
        default_days=settings.invite_default_expiry_days,
        default_max_uses=settings.invite_default_max_uses,
        now=datetime.now(timezone.utc),
    )


@router.post("/invites")
async def create_invite(request: Request, user: AdminUser, db: DbSession):
    form = await request.form()
    raw_ids = form.getlist("project_ids")
    project_ids = [int(str(x)) for x in raw_ids if x]
    if not project_ids:
        return RedirectResponse("/admin/invites?error=projects", status_code=303)
    try:
        expires_days = int(str(form.get("expires_days") or 14))
        max_uses = int(str(form.get("max_uses") or 50))
    except ValueError:
        expires_days, max_uses = 14, 50
    invite = project_service.create_invite(
        db,
        created_by=user,
        project_ids=project_ids,
        expires_days=expires_days,
        max_uses=max_uses,
    )
    return RedirectResponse(f"/admin/invites?created={invite.token}", status_code=303)


@router.post("/invites/{invite_id}/revoke")
def revoke_invite(invite_id: int, user: AdminUser, db: DbSession):
    invite = db.get(InviteLink, invite_id)
    if invite:
        project_service.revoke_invite(db, invite)
    return RedirectResponse("/admin/invites", status_code=303)
