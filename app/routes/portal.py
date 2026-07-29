from __future__ import annotations

import re
from collections.abc import Callable
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

from app.config import get_settings
from app.deps.auth import (
    CurrentUser,
    DbSession,
    get_last_project_key,
    get_optional_user,
    set_last_project_key,
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

_TICKET_REF_RE = re.compile(r"^([A-Z0-9]{1,5})-(\d+)$")
_MAX_TICKET_ATTACHMENTS = 3


def _upload_limit() -> str:
    return get_settings().upload_rate_limit


def _load_project(db: Session, key: str, user: User) -> Project:
    project = project_service.get_project_by_key_or_404(db, key)
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


def _header_ctx(db: Session, user: User, ticket: Ticket) -> dict:
    perms = ticket_service.get_ticket_permissions(db, user, ticket)
    members = (
        project_service.list_project_member_users(db, ticket.project)
        if ticket.project
        else []
    )
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
        "staff_members": [m for m in members if m.is_staff],
        "project_members": members,
        "project_tags": ticket_service.list_project_tags(db, ticket.project_id),
    }


def _ticket_mutation_response(
    request: Request, db: Session, user: User, ticket: Ticket
):
    if request.headers.get("HX-Request"):
        return render(
            request, "partials/ticket_view.html", **_header_ctx(db, user, ticket)
        )
    return RedirectResponse(ticket_path(ticket), status_code=303)


def _mutate_ticket(
    request: Request,
    db: Session,
    user: User,
    ticket_ref: str,
    mutator: Callable[[Ticket], Ticket],
    *,
    after: Callable[[Ticket], None] | None = None,
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = mutator(ticket)
    if after:
        after(ticket)
    return _ticket_mutation_response(request, db, user, ticket)


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


async def _attach_many(
    db: Session,
    attachments: list[UploadFile] | None,
    *,
    ticket_id: int,
    comment_id: int | None = None,
    max_files: int = _MAX_TICKET_ATTACHMENTS,
) -> None:
    if not attachments:
        return
    count = 0
    for attachment in attachments:
        if count >= max_files:
            break
        if not attachment or not attachment.filename:
            continue
        await _maybe_attach(db, attachment, ticket_id=ticket_id, comment_id=comment_id)
        count += 1


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: DbSession):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    projects = project_service.list_user_projects(db, user)
    if not projects:
        return render(request, "portal/empty.html", user=user)
    last_key = get_last_project_key(request)
    target = next((p for p in projects if p.key == last_key), projects[0])
    return RedirectResponse(project_path(target), status_code=303)


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
    set_last_project_key(request, project.key)
    projects = project_service.list_user_projects(db, user)
    current_view = view or "all"
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
    set_last_project_key(request, _project.key)
    projects = project_service.list_user_projects(db, user)
    return render(
        request,
        "portal/ticket.html",
        projects=projects,
        **_header_ctx(db, user, ticket),
    )


@router.post("/p/{key}/tickets")
@limiter.limit(_upload_limit)
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
    attachments: Annotated[list[UploadFile] | None, File()] = None,
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
    await _attach_many(db, attachments, ticket_id=ticket.id)
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
    attachments: Annotated[list[UploadFile] | None, File()] = None,
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    internal = bool(is_internal) and user.is_staff
    prev_assignee = ticket.assignee_id
    comment = ticket_service.add_comment(
        db, ticket, user, content, is_internal=internal
    )
    await _attach_many(db, attachments, ticket_id=ticket.id, comment_id=comment.id)
    ticket = ticket_service.get_ticket(db, ticket.id) or ticket
    notify_new_comment(background_tasks, db, ticket, user.id, is_internal=internal)
    auto_assigned = (
        not internal and prev_assignee is None and ticket.assignee_id == user.id
    )
    if auto_assigned:
        notify_assignment(background_tasks, ticket, user)
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/status", response_class=HTMLResponse)
def change_status(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    status: Annotated[str, Form()],
):
    try:
        new_status = TicketStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Nieprawidłowy status.") from None

    prev_status: TicketStatus | None = None

    def mutate(ticket: Ticket) -> Ticket:
        nonlocal prev_status
        prev_status = ticket.status
        return ticket_service.set_status(db, ticket, user, new_status)

    def after(ticket: Ticket) -> None:
        if ticket.status != prev_status:
            notify_status_change(background_tasks, db, ticket, user.id)

    return _mutate_ticket(request, db, user, ticket_ref, mutate, after=after)


@router.post("/t/{ticket_ref}/reopen", response_class=HTMLResponse)
def reopen_ticket(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
):
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda t: ticket_service.reopen_ticket(db, t, user),
        after=lambda t: notify_status_change(background_tasks, db, t, user.id),
    )


@router.post("/t/{ticket_ref}/edit", response_class=HTMLResponse)
@limiter.limit(_upload_limit)
async def edit_ticket(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
    remove_attachment_ids: Annotated[list[int] | None, Form()] = None,
):
    _project, ticket = _load_ticket(db, ticket_ref, user)
    ticket = ticket_service.update_ticket(
        db, ticket, user, title=title, description=description
    )
    if remove_attachment_ids:
        ticket = ticket_service.remove_ticket_attachments(
            db, ticket, user, remove_attachment_ids
        )
    remaining = max(0, _MAX_TICKET_ATTACHMENTS - len(ticket.attachments or []))
    await _attach_many(db, attachments, ticket_id=ticket.id, max_files=remaining)
    ticket = ticket_service.get_ticket(db, ticket.id) or ticket
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/priority", response_class=HTMLResponse)
def change_priority(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    priority: Annotated[str, Form()],
):
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda t: ticket_service.set_priority(db, t, user, TicketPriority(priority)),
    )


@router.post("/t/{ticket_ref}/type", response_class=HTMLResponse)
def change_type(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    ticket_type: Annotated[str, Form()],
):
    try:
        new_type = TicketType(ticket_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Nieprawidłowy typ.") from None
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda t: ticket_service.set_type(db, t, user, new_type),
    )


@router.post("/t/{ticket_ref}/tags", response_class=HTMLResponse)
def add_tag(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    name: Annotated[str, Form()],
):
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda t: ticket_service.add_ticket_tag(db, t, user, name),
    )


@router.post("/t/{ticket_ref}/tags/remove", response_class=HTMLResponse)
def remove_tag(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    tag_id: Annotated[int, Form()],
):
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda t: ticket_service.remove_ticket_tag(db, t, user, tag_id),
    )


@router.post("/t/{ticket_ref}/assign", response_class=HTMLResponse)
def assign(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    assignee_id: Annotated[str, Form()] = "",
):
    aid = int(assignee_id) if assignee_id else None

    def after(ticket: Ticket) -> None:
        if ticket.assignee:
            notify_assignment(background_tasks, ticket, ticket.assignee)

    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda t: ticket_service.assign_ticket(db, t, user, aid),
        after=after,
    )


@router.post("/t/{ticket_ref}/self-assign", response_class=HTMLResponse)
def self_assign(
    request: Request,
    ticket_ref: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
):
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda t: ticket_service.self_assign(db, t, user),
        after=lambda t: notify_assignment(background_tasks, t, user),
    )


@router.post("/t/{ticket_ref}/participants", response_class=HTMLResponse)
def add_participant(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    user_id: Annotated[int | None, Form()] = None,
):
    if user_id is None:
        raise HTTPException(status_code=400, detail="Wybierz użytkownika.")
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda t: ticket_service.add_participant(db, t, user, user_id),
    )
