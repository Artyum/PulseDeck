from __future__ import annotations

import re
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.deps.auth import (
    CurrentUser,
    DbSession,
    StaffUser,
    get_optional_user,
    set_user_session,
)
from app.models.enums import TicketPriority, TicketStatus, TicketType
from app.models.ticket import Ticket
from app.models.user import Project, User
from app.rate_limit import limiter
from app.routes.context import render
from app.services import projects as project_service
from app.services import tickets as ticket_service
from app.services.email import (
    notify_assignment,
    notify_new_comment,
    notify_new_ticket,
    notify_status_change,
)
from app.services.uploads import save_upload
from app.utils.urls import project_path, ticket_path

router = APIRouter(tags=["portal"])

_TICKET_REF_RE = re.compile(r"^([A-Z0-9]{3,10})-(\d+)$")


def _load_project(db: Session, key: str, user: User) -> Project:
    project = project_service.get_project_by_key(db, key)
    if not project:
        raise HTTPException(status_code=404, detail="Nie znaleziono")
    ticket_service.require_project_access(db, user, project.id)
    return project


def _parse_ticket_ref(ticket_ref: str) -> tuple[str, int]:
    match = _TICKET_REF_RE.fullmatch((ticket_ref or "").strip().upper())
    if not match:
        raise HTTPException(status_code=404, detail="Nie znaleziono")
    return match.group(1), int(match.group(2))


def _load_ticket(db: Session, ticket_ref: str, user: User) -> tuple[Project, Ticket]:
    key, ticket_id = _parse_ticket_ref(ticket_ref)
    ticket = ticket_service.get_ticket(db, ticket_id)
    if not ticket or not ticket.project or ticket.project.key != key:
        raise HTTPException(status_code=404, detail="Nie znaleziono")
    ticket_service.require_project_access(db, user, ticket.project_id)
    return ticket.project, ticket


def _staff_members_for(ticket: Ticket) -> list:
    members = [m.user for m in (ticket.project.members if ticket.project else [])]
    return [m for m in members if m and m.is_staff]


def _header_ctx(db: Session, user: User, ticket: Ticket) -> dict:
    perms = ticket_service.get_ticket_permissions(db, user, ticket)
    return {
        "user": user,
        "ticket": ticket,
        "project": ticket.project,
        "can_assign": perms.can_assign,
        "can_set_done": perms.can_set_done,
        "can_reopen": perms.can_reopen,
        "can_edit": perms.can_edit,
        "can_manage_tags": perms.can_manage_tags,
        "can_comment": perms.can_comment,
        "staff_members": _staff_members_for(ticket),
        "project_tags": ticket_service.list_project_tags(db, ticket.project_id),
    }


def _ticket_mutation_response(
    request: Request, db: Session, user: User, ticket: Ticket
):
    if request.headers.get("HX-Request"):
        return render(
            request, "partials/ticket_header.html", **_header_ctx(db, user, ticket)
        )
    return RedirectResponse(ticket_path(ticket), status_code=303)


async def _maybe_attach(
    db: Session,
    attachment: UploadFile | None,
    *,
    ticket_id: int,
    comment_id: int | None = None,
) -> None:
    if not attachment or not attachment.filename:
        return
    original, rel = await save_upload(attachment, subdir=f"tickets/{ticket_id}")
    ticket_service.add_attachment(
        db,
        file_name=original,
        file_path=rel,
        ticket_id=None if comment_id else ticket_id,
        comment_id=comment_id,
    )


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: DbSession):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    projects = project_service.list_user_projects(db, user)
    if not projects:
        return render(request, "portal/empty.html", user=user)
    return RedirectResponse(project_path(projects[0]), status_code=303)


@router.get("/inbox", response_class=HTMLResponse)
def staff_inbox(
    request: Request,
    user: StaffUser,
    db: DbSession,
    view: str = "needs_us",
):
    projects = project_service.list_user_projects(db, user)
    tickets = ticket_service.list_inbox_tickets(db, user, view=view)
    return render(
        request,
        "portal/inbox.html",
        user=user,
        projects=projects,
        tickets=tickets,
        current_view=view,
    )


@router.get("/p/{key}", response_class=HTMLResponse)
def project_feed(
    request: Request,
    key: str,
    user: CurrentUser,
    db: DbSession,
    view: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    sort: str | None = None,
):
    project = _load_project(db, key, user)
    projects = project_service.list_user_projects(db, user)
    current_view = view or ticket_service.default_feed_view(user)
    tickets = ticket_service.list_tickets(
        db,
        project.id,
        user=user,
        view=current_view,
        status_filter=status,
        priority_filter=priority,
        tag=tag,
        q=q,
        sort=sort,
    )
    return render(
        request,
        "portal/feed.html",
        user=user,
        project=project,
        projects=projects,
        tickets=tickets,
        current_view=current_view,
        filter_status=status or "",
        filter_priority=priority or "",
        filter_tag=tag or "",
        filter_q=q or "",
        filter_sort=sort or "updated_at",
        project_tags=ticket_service.list_project_tags(db, project.id),
    )


@router.get("/t/{ticket_ref}", response_class=HTMLResponse)
def ticket_detail(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    projects = project_service.list_user_projects(db, user)
    members = [m.user for m in (ticket.project.members if ticket.project else [])]
    return render(
        request,
        "portal/ticket.html",
        projects=projects,
        project_members=members,
        **_header_ctx(db, user, ticket),
    )


@router.post("/p/{key}/tickets")
@limiter.limit("20/minute")
async def create_ticket(
    request: Request,
    key: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],
    ticket_type: Annotated[str, Form()],
    priority: Annotated[str, Form()] = "NORMAL",
    attachment: Annotated[UploadFile | None, File()] = None,
):
    project = _load_project(db, key, user)
    try:
        prio = TicketPriority(priority)
    except ValueError:
        prio = TicketPriority.NORMAL
    ticket = ticket_service.create_ticket(
        db,
        project_id=project.id,
        author=user,
        title=title,
        description=description,
        ticket_type=TicketType(ticket_type),
        priority=prio,
    )
    await _maybe_attach(db, attachment, ticket_id=ticket.id)
    ticket = ticket_service.get_ticket(db, ticket.id) or ticket
    notify_new_ticket(background_tasks, db, ticket)
    return RedirectResponse(ticket_path(ticket), status_code=303)


@router.post("/t/{ticket_ref}/comments", response_class=HTMLResponse)
async def add_comment(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    content: Annotated[str, Form()],
    is_internal: Annotated[str, Form()] = "",
    attachment: Annotated[UploadFile | None, File()] = None,
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    internal = bool(is_internal) and user.is_staff
    prev_assignee = ticket.assignee_id
    comment = ticket_service.add_comment(
        db, ticket, user, content, is_internal=internal
    )
    await _maybe_attach(db, attachment, ticket_id=ticket.id, comment_id=comment.id)
    ticket = ticket_service.get_ticket(db, ticket.id) or ticket
    notify_new_comment(background_tasks, db, ticket, user.id, is_internal=internal)
    if not internal and prev_assignee is None and ticket.assignee_id == user.id:
        notify_assignment(background_tasks, ticket, user)
    perms = ticket_service.get_ticket_permissions(db, user, ticket)
    return render(
        request,
        "partials/thread.html",
        user=user,
        ticket=ticket,
        can_comment=perms.can_comment,
        can_reopen=perms.can_reopen,
    )


@router.post("/t/{ticket_ref}/status", response_class=HTMLResponse)
def change_status(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    status: Annotated[str, Form()],
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = ticket_service.set_status(db, ticket, user, TicketStatus(status))
    notify_status_change(background_tasks, db, ticket, user.id)
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/reopen", response_class=HTMLResponse)
def reopen_ticket(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = ticket_service.reopen_ticket(db, ticket, user)
    notify_status_change(background_tasks, db, ticket, user.id)
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/edit")
def edit_ticket(
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = ticket_service.update_ticket(
        db, ticket, user, title=title, description=description
    )
    return RedirectResponse(ticket_path(ticket), status_code=303)


@router.post("/t/{ticket_ref}/priority", response_class=HTMLResponse)
def change_priority(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    priority: Annotated[str, Form()],
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = ticket_service.set_priority(db, ticket, user, TicketPriority(priority))
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/tags", response_class=HTMLResponse)
def add_tag(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    name: Annotated[str, Form()],
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = ticket_service.add_ticket_tag(db, ticket, user, name)
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/tags/remove", response_class=HTMLResponse)
def remove_tag(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    tag_id: Annotated[int, Form()],
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = ticket_service.remove_ticket_tag(db, ticket, user, tag_id)
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/assign", response_class=HTMLResponse)
def assign(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    assignee_id: Annotated[str, Form()] = "",
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    aid = int(assignee_id) if assignee_id else None
    ticket = ticket_service.assign_ticket(db, ticket, user, aid)
    if ticket.assignee:
        notify_assignment(background_tasks, ticket, ticket.assignee)
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/self-assign", response_class=HTMLResponse)
def self_assign(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = ticket_service.self_assign(db, ticket, user)
    notify_assignment(background_tasks, ticket, user)
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/participants")
def add_participant(
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    user_id: Annotated[int, Form()],
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket_service.add_participant(db, ticket, user, user_id)
    return RedirectResponse(ticket_path(ticket), status_code=303)


@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_page(request: Request, token: str, db: DbSession):
    invite = project_service.get_invite_by_token(db, token)
    if not invite or not invite.is_valid:
        return render(request, "auth/invite_invalid.html")
    projects = [lp.project for lp in invite.projects if lp.project]
    return render(
        request, "auth/invite.html", invite=invite, projects=projects, error=None
    )


@router.post("/invite/{token}")
@limiter.limit("5/minute")
def invite_register(
    request: Request,
    token: str,
    db: DbSession,
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    invite = project_service.get_invite_by_token(db, token)
    if not invite or not invite.is_valid:
        return render(request, "auth/invite_invalid.html")
    projects = [lp.project for lp in invite.projects if lp.project]
    try:
        user = project_service.register_via_invite(
            db,
            invite,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
        )
    except ValueError as exc:
        return render(
            request,
            "auth/invite.html",
            invite=invite,
            projects=projects,
            error=str(exc),
        )
    set_user_session(request, user)
    return RedirectResponse("/", status_code=303)
