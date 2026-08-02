from __future__ import annotations

import re
from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
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
    notify_ticket_update,
)
from app.services.uploads import (
    file_response_for_attachment,
    get_attachment_for_download,
    save_upload,
)
from app.utils.i18n import resolve_lang, t
from app.utils.urls import project_path, ticket_path

router = APIRouter(tags=["portal"])

_TICKET_REF_RE = re.compile(r"^([A-Z0-9]{1,5})-(\d+)$")
_MAX_TICKET_ATTACHMENTS = 3


def _upload_limit() -> str:
    return get_settings().upload_rate_limit


def _load_project(db: Session, key: str, user: User, *, lang: str) -> Project:
    project = project_service.get_project_by_key_or_404(
        db, key, lang=lang, require_active=True
    )
    ticket_service.require_project_access(db, user, project.id, lang=lang)
    return project


def _parse_ticket_ref(ticket_ref: str, *, lang: str) -> tuple[str, int]:
    match = _TICKET_REF_RE.fullmatch((ticket_ref or "").strip().upper())
    if not match:
        raise HTTPException(status_code=404, detail=t(lang, "messages.http.not_found"))
    return match.group(1), int(match.group(2))


def _load_ticket(
    db: Session, ticket_ref: str, user: User, *, lang: str
) -> tuple[Project, Ticket]:
    key, number = _parse_ticket_ref(ticket_ref, lang=lang)
    project = _load_project(db, key, user, lang=lang)
    ticket = ticket_service.get_ticket_by_project_number(db, project.id, number)
    if not ticket:
        raise HTTPException(status_code=404, detail=t(lang, "messages.http.not_found"))
    return project, ticket


def _header_ctx(db: Session, user: User, ticket: Ticket) -> dict:
    perms = ticket_service.get_ticket_permissions(db, user, ticket)
    members = (
        project_service.list_project_member_users(db, ticket.project)
        if ticket.project
        else []
    )
    members = sorted(
        members,
        key=lambda u: (
            (u.first_name or "").casefold(),
            (u.last_name or "").casefold(),
        ),
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
        "can_edit_comments": perms.can_edit_comments,
        "can_delete_comments": perms.can_delete_comments,
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
    lang = resolve_lang(request)
    _project, ticket = _load_ticket(db, ticket_ref, user, lang=lang)
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
    lang: str,
) -> None:
    if not attachment or not attachment.filename:
        return
    original, rel = await save_upload(
        attachment, subdir=f"tickets/{ticket_id}", lang=lang
    )
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
    lang: str,
) -> None:
    if not attachments:
        return
    count = 0
    for attachment in attachments:
        if count >= max_files:
            break
        if not attachment or not attachment.filename:
            continue
        await _maybe_attach(
            db, attachment, ticket_id=ticket_id, comment_id=comment_id, lang=lang
        )
        count += 1


@router.get("/files/{attachment_id}")
def download_attachment(
    request: Request,
    attachment_id: int,
    user: CurrentUser,
    db: DbSession,
):
    lang = resolve_lang(request)
    att = get_attachment_for_download(db, attachment_id, user, lang=lang)
    return file_response_for_attachment(att, lang=lang)


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
    type: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    sort: str | None = None,
):
    lang = resolve_lang(request)
    project = _load_project(db, key, user, lang=lang)
    set_last_project_key(request, project.key)
    projects = project_service.list_user_projects(db, user)
    current_view = view or ("all" if user.is_staff else "mine")
    tickets = ticket_service.list_tickets(
        db,
        project.id,
        user=user,
        view=current_view,
        status_filter=status,
        priority_filter=priority,
        type_filter=type,
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
        filter_type=type or "",
        filter_tag=tag or "",
        filter_q=q or "",
        filter_sort=sort or "updated_at",
        project_tags=project_service.list_used_project_tags(db, project.id),
    )


@router.get("/t/{ticket_ref}", response_class=HTMLResponse)
def ticket_detail(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
):
    lang = resolve_lang(request)
    _project, ticket = _load_ticket(db, ticket_ref, user, lang=lang)
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
    user: CurrentUser,
    db: DbSession,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],
    ticket_type: Annotated[str, Form()],
    priority: Annotated[str, Form()] = "NORMAL",
    attachments: Annotated[list[UploadFile] | None, File()] = None,
):
    lang = resolve_lang(request)
    project = _load_project(db, key, user, lang=lang)
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
        lang=lang,
    )
    await _attach_many(db, attachments, ticket_id=ticket.id, lang=lang)
    ticket = ticket_service.get_ticket(db, ticket.id) or ticket
    notify_new_ticket(db, ticket)
    return RedirectResponse(ticket_path(ticket), status_code=303)


@router.post("/t/{ticket_ref}/comments", response_class=HTMLResponse)
@limiter.limit(_upload_limit)
async def add_comment(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    content: Annotated[str, Form()],
    is_internal: Annotated[str, Form()] = "",
    attachments: Annotated[list[UploadFile] | None, File()] = None,
):
    lang = resolve_lang(request)
    _project, ticket = _load_ticket(db, ticket_ref, user, lang=lang)
    internal = bool(is_internal) and user.is_staff
    comment = ticket_service.add_comment(
        db, ticket, user, content, is_internal=internal, lang=lang
    )
    await _attach_many(
        db, attachments, ticket_id=ticket.id, comment_id=comment.id, lang=lang
    )
    ticket = ticket_service.get_ticket(db, ticket.id) or ticket
    notify_new_comment(db, ticket, user.id, is_internal=internal)
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/comments/{comment_id}/edit", response_class=HTMLResponse)
def edit_comment(
    request: Request,
    ticket_ref: str,
    comment_id: int,
    user: CurrentUser,
    db: DbSession,
    content: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    _project, ticket = _load_ticket(db, ticket_ref, user, lang=lang)
    ticket_service.update_comment(db, ticket, comment_id, user, content, lang=lang)
    ticket = ticket_service.get_ticket(db, ticket.id) or ticket
    return _ticket_mutation_response(request, db, user, ticket)


@router.post(
    "/t/{ticket_ref}/comments/{comment_id}/delete", response_class=HTMLResponse
)
def delete_comment(
    request: Request,
    ticket_ref: str,
    comment_id: int,
    user: CurrentUser,
    db: DbSession,
):
    lang = resolve_lang(request)
    _project, ticket = _load_ticket(db, ticket_ref, user, lang=lang)
    ticket_service.delete_comment(db, ticket, comment_id, user, lang=lang)
    ticket = ticket_service.get_ticket(db, ticket.id) or ticket
    return _ticket_mutation_response(request, db, user, ticket)


@router.post("/t/{ticket_ref}/status", response_class=HTMLResponse)
def change_status(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    status: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    try:
        new_status = TicketStatus(status)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=t(lang, "messages.tickets.invalid_status")
        ) from None

    prev_status: TicketStatus | None = None

    def mutate(ticket: Ticket) -> Ticket:
        nonlocal prev_status
        prev_status = ticket.status
        return ticket_service.set_status(db, ticket, user, new_status, lang=lang)

    def after(ticket: Ticket) -> None:
        if ticket.status != prev_status:
            notify_ticket_update(
                db,
                ticket,
                user.id,
                change_key=f"enums.ticket_status.{ticket.status.value}",
            )

    return _mutate_ticket(request, db, user, ticket_ref, mutate, after=after)


@router.post("/t/{ticket_ref}/reopen", response_class=HTMLResponse)
def reopen_ticket(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
):
    lang = resolve_lang(request)

    def after(ticket: Ticket) -> None:
        notify_ticket_update(
            db,
            ticket,
            user.id,
            change_key=f"enums.ticket_status.{ticket.status.value}",
        )

    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda ticket: ticket_service.reopen_ticket(db, ticket, user, lang=lang),
        after=after,
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
    lang = resolve_lang(request)
    _project, ticket = _load_ticket(db, ticket_ref, user, lang=lang)
    ticket = ticket_service.update_ticket(
        db, ticket, user, title=title, description=description, lang=lang
    )
    if remove_attachment_ids:
        ticket = ticket_service.remove_ticket_attachments(
            db, ticket, user, remove_attachment_ids, lang=lang
        )
    remaining = max(0, _MAX_TICKET_ATTACHMENTS - len(ticket.attachments or []))
    await _attach_many(
        db, attachments, ticket_id=ticket.id, max_files=remaining, lang=lang
    )
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
    lang = resolve_lang(request)
    try:
        new_priority = TicketPriority(priority)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=t(lang, "messages.tickets.invalid_priority")
        ) from None

    prev: TicketPriority | None = None

    def mutate(ticket: Ticket) -> Ticket:
        nonlocal prev
        prev = ticket.priority
        return ticket_service.set_priority(db, ticket, user, new_priority, lang=lang)

    def after(ticket: Ticket) -> None:
        if prev is not None and ticket.priority != prev:
            notify_ticket_update(
                db,
                ticket,
                user.id,
                change_key=f"enums.ticket_priority.{ticket.priority.value}",
            )

    return _mutate_ticket(request, db, user, ticket_ref, mutate, after=after)


@router.post("/t/{ticket_ref}/type", response_class=HTMLResponse)
def change_type(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    ticket_type: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    try:
        new_type = TicketType(ticket_type)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=t(lang, "messages.tickets.invalid_type")
        ) from None

    prev: TicketType | None = None

    def mutate(ticket: Ticket) -> Ticket:
        nonlocal prev
        prev = ticket.type
        return ticket_service.set_type(db, ticket, user, new_type, lang=lang)

    def after(ticket: Ticket) -> None:
        if prev is not None and ticket.type != prev:
            notify_ticket_update(
                db,
                ticket,
                user.id,
                change_key=f"enums.ticket_type.{ticket.type.value}",
            )

    return _mutate_ticket(request, db, user, ticket_ref, mutate, after=after)


@router.post("/t/{ticket_ref}/tags", response_class=HTMLResponse)
def add_tag(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    name: Annotated[str, Form()],
):
    lang = resolve_lang(request)
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda ticket: ticket_service.add_ticket_tag(db, ticket, user, name, lang=lang),
    )


@router.post("/t/{ticket_ref}/tags/remove", response_class=HTMLResponse)
def remove_tag(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    tag_id: Annotated[int, Form()],
):
    lang = resolve_lang(request)
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda ticket: ticket_service.remove_ticket_tag(
            db, ticket, user, tag_id, lang=lang
        ),
    )


@router.post("/t/{ticket_ref}/assign", response_class=HTMLResponse)
def assign(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    assignee_id: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    aid = int(assignee_id) if assignee_id else None
    previous: User | None = None

    def mutate(ticket: Ticket) -> Ticket:
        nonlocal previous
        previous = ticket.assignee
        return ticket_service.assign_ticket(db, ticket, user, aid, lang=lang)

    def after(ticket: Ticket) -> None:
        notify_assignment(
            db,
            ticket,
            actor_id=user.id,
            previous=previous,
            new=ticket.assignee,
        )

    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        mutate,
        after=after,
    )


@router.post("/t/{ticket_ref}/reporter", response_class=HTMLResponse)
def change_reporter(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    author_id: Annotated[int, Form()],
):
    lang = resolve_lang(request)
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda ticket: ticket_service.change_reporter(
            db, ticket, user, author_id, lang=lang
        ),
    )


@router.post("/t/{ticket_ref}/self-assign", response_class=HTMLResponse)
def self_assign(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
):
    lang = resolve_lang(request)
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda ticket: ticket_service.self_assign(db, ticket, user, lang=lang),
    )


@router.post("/t/{ticket_ref}/participants", response_class=HTMLResponse)
def add_participant(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    user_id: Annotated[int | None, Form()] = None,
):
    lang = resolve_lang(request)
    if user_id is None:
        raise HTTPException(
            status_code=400, detail=t(lang, "messages.tickets.select_user")
        )
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda ticket: ticket_service.add_participant(
            db, ticket, user, user_id, lang=lang
        ),
    )


@router.post("/t/{ticket_ref}/unwatch", response_class=HTMLResponse)
def stop_watching(
    request: Request,
    ticket_ref: str,
    user: CurrentUser,
    db: DbSession,
    user_id: Annotated[int | None, Form()] = None,
):
    lang = resolve_lang(request)
    return _mutate_ticket(
        request,
        db,
        user,
        ticket_ref,
        lambda ticket: ticket_service.remove_participant(
            db, ticket, user, user_id, lang=lang
        ),
    )
