from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.enums import TicketPriority, TicketStatus, TicketType
from app.models.ticket import (
    Attachment,
    Comment,
    Tag,
    Ticket,
    TicketParticipant,
    TicketTag,
)
from app.models.user import Project, ProjectMember, User
from app.services.projects import is_project_member
from app.utils.i18n import DEFAULT_LANG, t
from app.validation import clean, clean_many

logger = logging.getLogger("pulsedeck.app.tickets")


def _clean_or_400(field_id: str, value, *, lang: str):
    try:
        return clean(field_id, value, lang=lang)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _clean_many_or_400(values: dict, *, lang: str) -> dict:
    try:
        return clean_many(values, lang=lang)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


_OPEN_STATUSES = (
    TicketStatus.NEW,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_ON_CLIENT,
)
_NEEDS_US_STATUSES = (TicketStatus.NEW, TicketStatus.IN_PROGRESS)

_TICKET_LOAD = (
    selectinload(Ticket.author),
    selectinload(Ticket.assignee),
    selectinload(Ticket.comments).selectinload(Comment.author),
    selectinload(Ticket.comments).selectinload(Comment.edited_by),
    selectinload(Ticket.comments).selectinload(Comment.attachments),
    selectinload(Ticket.participants).selectinload(TicketParticipant.user),
    selectinload(Ticket.attachments),
    selectinload(Ticket.project)
    .selectinload(Project.members)
    .selectinload(ProjectMember.user),
    selectinload(Ticket.ticket_tags).selectinload(TicketTag.tag),
)


@dataclass(frozen=True)
class TicketPermissions:
    can_assign: bool
    can_set_done: bool
    can_reopen: bool
    can_edit: bool
    can_manage_tags: bool
    can_comment: bool
    can_edit_comments: bool
    can_delete_comments: bool


def _is_member(db: Session, user: User, ticket: Ticket, member: bool | None) -> bool:
    if member is not None:
        return member
    return is_project_member(db, ticket.project_id, user.id)


def can_comment(
    db: Session, user: User, ticket: Ticket, *, member: bool | None = None
) -> bool:
    if ticket.status == TicketStatus.DONE:
        return False
    return _is_member(db, user, ticket, member)


def can_edit_comments(user: User) -> bool:
    return user.is_staff


def can_delete_comments(user: User) -> bool:
    return user.is_admin


def can_assign(
    user: User, ticket: Ticket, db: Session, *, member: bool | None = None
) -> bool:
    return user.is_staff and _is_member(db, user, ticket, member)


def can_set_done(
    user: User, ticket: Ticket, db: Session, *, member: bool | None = None
) -> bool:
    if not _is_member(db, user, ticket, member):
        return False
    return user.is_staff or ticket.author_id == user.id


def can_reopen(
    user: User, ticket: Ticket, db: Session, *, member: bool | None = None
) -> bool:
    if ticket.status != TicketStatus.DONE:
        return False
    if not _is_member(db, user, ticket, member):
        return False
    if user.is_staff:
        return True
    if ticket.closed_at is None:
        return False
    settings = get_settings()
    closed = ticket.closed_at
    if closed.tzinfo is None:
        closed = closed.replace(tzinfo=timezone.utc)
    deadline = closed + timedelta(days=settings.ticket_reopen_days)
    return datetime.now(timezone.utc) <= deadline


def can_edit_ticket(
    user: User, ticket: Ticket, db: Session, *, member: bool | None = None
) -> bool:
    if not _is_member(db, user, ticket, member):
        return False
    if user.is_staff:
        return True
    return ticket.author_id == user.id and ticket.status == TicketStatus.NEW


def can_manage_tags(
    user: User, ticket: Ticket, db: Session, *, member: bool | None = None
) -> bool:
    return can_assign(user, ticket, db, member=member)


def get_ticket_permissions(
    db: Session, user: User, ticket: Ticket
) -> TicketPermissions:
    member = is_project_member(db, ticket.project_id, user.id)
    return TicketPermissions(
        can_assign=can_assign(user, ticket, db, member=member),
        can_set_done=can_set_done(user, ticket, db, member=member),
        can_reopen=can_reopen(user, ticket, db, member=member),
        can_edit=can_edit_ticket(user, ticket, db, member=member),
        can_manage_tags=can_manage_tags(user, ticket, db, member=member),
        can_comment=can_comment(db, user, ticket, member=member),
        can_edit_comments=can_edit_comments(user),
        can_delete_comments=can_delete_comments(user),
    )


def require_project_access(
    db: Session, user: User, project_id: int, *, lang: str | None = None
) -> None:
    if not is_project_member(db, project_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.no_project_access"),
        )


def _apply_view_filter(stmt, *, view: str | None, user: User, staff: bool):
    if not view or view == "all":
        return stmt
    if staff:
        if view == "unassigned":
            return stmt.where(
                Ticket.assignee_id.is_(None), Ticket.status.in_(_OPEN_STATUSES)
            )
        if view == "mine_open":
            return stmt.where(
                Ticket.assignee_id == user.id, Ticket.status.in_(_OPEN_STATUSES)
            )
        if view == "needs_us":
            return stmt.where(Ticket.status.in_(_NEEDS_US_STATUSES))
        if view == "done":
            return stmt.where(Ticket.status == TicketStatus.DONE)
    else:
        if view == "mine":
            return stmt.where(Ticket.author_id == user.id)
        if view == "waiting_on_me":
            return stmt.where(Ticket.status == TicketStatus.WAITING_ON_CLIENT)
        if view == "done":
            return stmt.where(Ticket.status == TicketStatus.DONE)
    return stmt


def _apply_sort(stmt, sort: str | None):
    if sort == "created_at":
        return stmt.order_by(Ticket.created_at.desc())
    if sort == "priority":
        priority_order = case(
            (Ticket.priority == TicketPriority.HIGH, 0),
            (Ticket.priority == TicketPriority.NORMAL, 1),
            else_=2,
        )
        return stmt.order_by(priority_order, Ticket.updated_at.desc())
    return stmt.order_by(Ticket.updated_at.desc())


def list_tickets(
    db: Session,
    project_id: int,
    *,
    user: User,
    view: str | None = None,
    status_filter: str | None = None,
    priority_filter: str | None = None,
    type_filter: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    sort: str | None = None,
) -> list[Ticket]:
    stmt = select(Ticket).where(Ticket.project_id == project_id)
    stmt = _apply_view_filter(stmt, view=view, user=user, staff=user.is_staff)
    if status_filter:
        try:
            stmt = stmt.where(Ticket.status == TicketStatus(status_filter))
        except ValueError:
            pass
    if priority_filter:
        try:
            stmt = stmt.where(Ticket.priority == TicketPriority(priority_filter))
        except ValueError:
            pass
    if type_filter:
        try:
            stmt = stmt.where(Ticket.type == TicketType(type_filter))
        except ValueError:
            pass
    if tag:
        tag = _clean_or_400("filter.tag", tag, lang=DEFAULT_LANG)
    if tag:
        stmt = (
            stmt.join(TicketTag, TicketTag.ticket_id == Ticket.id)
            .join(Tag, Tag.id == TicketTag.tag_id)
            .where(func.lower(Tag.name) == tag.lower())
        )
    if q:
        raw = _clean_or_400("search.q", q, lang=DEFAULT_LANG)
        if raw:
            title_match = Ticket.title.ilike(f"%{raw}%")
            ref = re.fullmatch(r"(?:[A-Za-z0-9]{1,5}-)?(\d+)", raw, flags=re.IGNORECASE)
            if ref:
                stmt = stmt.where(or_(title_match, Ticket.number == int(ref.group(1))))
            else:
                stmt = stmt.where(title_match)
    stmt = stmt.options(
        selectinload(Ticket.author),
        selectinload(Ticket.assignee),
        selectinload(Ticket.project),
        selectinload(Ticket.ticket_tags).selectinload(TicketTag.tag),
    ).distinct()
    stmt = _apply_sort(stmt, sort)
    return list(db.scalars(stmt).all())


def get_ticket(db: Session, ticket_id: int) -> Ticket | None:
    return db.scalar(
        select(Ticket).where(Ticket.id == ticket_id).options(*_TICKET_LOAD)
    )


def get_ticket_by_project_number(
    db: Session, project_id: int, number: int
) -> Ticket | None:
    return db.scalar(
        select(Ticket)
        .where(Ticket.project_id == project_id, Ticket.number == number)
        .options(*_TICKET_LOAD)
    )


def create_ticket(
    db: Session,
    *,
    project_id: int,
    author: User,
    title: str,
    description: str,
    ticket_type: TicketType,
    priority: TicketPriority = TicketPriority.NORMAL,
    lang: str | None = None,
) -> Ticket:
    lang = lang or DEFAULT_LANG
    data = _clean_many_or_400(
        {
            "ticket.title": title,
            "ticket.description": description,
        },
        lang=lang,
    )
    project = db.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t(lang, "messages.http.not_found"),
        )
    next_number = (
        db.scalar(
            select(func.coalesce(func.max(Ticket.number), 0)).where(
                Ticket.project_id == project_id
            )
        )
        or 0
    ) + 1
    ticket = Ticket(
        project_id=project_id,
        number=next_number,
        author_id=author.id,
        title=data["ticket.title"],
        description=data["ticket.description"],
        type=ticket_type,
        priority=priority,
        status=TicketStatus.NEW,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return get_ticket(db, ticket.id) or ticket


def _ensure_participant(db: Session, ticket: Ticket, user_id: int) -> None:
    if ticket.author_id == user_id:
        return
    existing = db.scalar(
        select(TicketParticipant).where(
            TicketParticipant.ticket_id == ticket.id,
            TicketParticipant.user_id == user_id,
        )
    )
    if existing:
        return
    db.add(TicketParticipant(ticket_id=ticket.id, user_id=user_id))


def add_comment(
    db: Session,
    ticket: Ticket,
    author: User,
    content: str,
    *,
    is_internal: bool = False,
    lang: str | None = None,
    commit: bool = True,
) -> Comment:
    lang = lang or DEFAULT_LANG
    if not can_comment(db, author, ticket):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_comment")
        )
    if is_internal and not author.is_staff:
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.internal_staff_only")
        )
    text = _clean_or_400("comment.content", content, lang=lang)
    comment = Comment(
        ticket_id=ticket.id,
        author_id=author.id,
        content=text,
        is_internal=bool(is_internal),
    )
    db.add(comment)
    if not is_internal:
        _ensure_participant(db, ticket, author.id)
        if author.is_staff:
            ticket.status = TicketStatus.WAITING_ON_CLIENT
            if ticket.assignee_id is None:
                ticket.assignee_id = author.id
        else:
            ticket.status = TicketStatus.IN_PROGRESS
    if commit:
        db.commit()
        db.refresh(comment)
    else:
        db.flush()
    return comment


def _get_ticket_comment(
    db: Session, ticket: Ticket, comment_id: int, *, lang: str
) -> Comment:
    comment = db.scalar(
        select(Comment)
        .where(Comment.id == comment_id, Comment.ticket_id == ticket.id)
        .options(selectinload(Comment.attachments))
    )
    if not comment:
        raise HTTPException(
            status_code=404, detail=t(lang, "messages.tickets.comment_not_found")
        )
    return comment


def update_comment(
    db: Session,
    ticket: Ticket,
    comment_id: int,
    actor: User,
    content: str,
    *,
    lang: str | None = None,
) -> Comment:
    lang = lang or DEFAULT_LANG
    if not can_edit_comments(actor):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_edit_comment")
        )
    text = _clean_or_400("comment.content", content, lang=lang)
    comment = _get_ticket_comment(db, ticket, comment_id, lang=lang)
    comment.content = text
    comment.edited_at = datetime.now(timezone.utc)
    comment.edited_by_id = actor.id
    db.commit()
    db.refresh(comment)
    return comment


def delete_comment(
    db: Session,
    ticket: Ticket,
    comment_id: int,
    actor: User,
    *,
    lang: str | None = None,
) -> None:
    lang = lang or DEFAULT_LANG
    if not can_delete_comments(actor):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_delete_comment")
        )
    comment = _get_ticket_comment(db, ticket, comment_id, lang=lang)
    file_paths = [a.file_path for a in comment.attachments if a.file_path]
    db.delete(comment)
    db.commit()
    from app.services.uploads import resolve_safe_upload_path

    for rel in file_paths:
        path = resolve_safe_upload_path(rel)
        if path is None:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to delete attachment file %s", rel, exc_info=True)


def assign_ticket(
    db: Session,
    ticket: Ticket,
    actor: User,
    assignee_id: int | None,
    *,
    lang: str | None = None,
) -> Ticket:
    lang = lang or DEFAULT_LANG
    if not can_assign(actor, ticket, db):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_assign")
        )
    if assignee_id is not None:
        assignee = db.get(User, assignee_id)
        if not assignee or not assignee.is_staff:
            raise HTTPException(
                status_code=400,
                detail=t(lang, "messages.tickets.assignee_must_be_staff"),
            )
        if not is_project_member(db, ticket.project_id, assignee.id):
            raise HTTPException(
                status_code=400,
                detail=t(lang, "messages.tickets.assignee_must_be_member"),
            )
        ticket.assignee_id = assignee.id
        if ticket.status == TicketStatus.NEW:
            ticket.status = TicketStatus.IN_PROGRESS
    else:
        ticket.assignee_id = None
    db.commit()
    return get_ticket(db, ticket.id) or ticket


def self_assign(
    db: Session, ticket: Ticket, actor: User, *, lang: str | None = None
) -> Ticket:
    return assign_ticket(db, ticket, actor, actor.id, lang=lang)


def change_reporter(
    db: Session,
    ticket: Ticket,
    actor: User,
    author_id: int,
    *,
    lang: str | None = None,
) -> Ticket:
    lang = lang or DEFAULT_LANG
    if not can_assign(actor, ticket, db):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_change_reporter")
        )
    if author_id == ticket.author_id:
        return get_ticket(db, ticket.id) or ticket
    author = db.get(User, author_id)
    if not author or not is_project_member(db, ticket.project_id, author.id):
        raise HTTPException(
            status_code=400,
            detail=t(lang, "messages.tickets.reporter_must_be_member"),
        )
    row = db.scalar(
        select(TicketParticipant).where(
            TicketParticipant.ticket_id == ticket.id,
            TicketParticipant.user_id == author_id,
        )
    )
    if row:
        db.delete(row)
    ticket.author_id = author.id
    db.commit()
    return get_ticket(db, ticket.id) or ticket


def set_status(
    db: Session,
    ticket: Ticket,
    actor: User,
    status_value: TicketStatus,
    *,
    lang: str | None = None,
) -> Ticket:
    lang = lang or DEFAULT_LANG
    if not is_project_member(db, ticket.project_id, actor.id):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_project_access")
        )

    if status_value == ticket.status:
        return ticket

    if actor.is_staff:
        ticket.status = status_value
        ticket.closed_at = (
            datetime.now(timezone.utc) if status_value == TicketStatus.DONE else None
        )
        db.commit()
        return get_ticket(db, ticket.id) or ticket

    if status_value == TicketStatus.DONE and can_set_done(actor, ticket, db):
        ticket.status = TicketStatus.DONE
        ticket.closed_at = datetime.now(timezone.utc)
        db.commit()
        return get_ticket(db, ticket.id) or ticket

    raise HTTPException(status_code=403, detail=t(lang, "messages.tickets.no_status"))


def reopen_ticket(
    db: Session, ticket: Ticket, actor: User, *, lang: str | None = None
) -> Ticket:
    if not can_reopen(actor, ticket, db):
        raise HTTPException(
            status_code=403,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.cannot_reopen"),
        )
    ticket.status = TicketStatus.IN_PROGRESS
    ticket.closed_at = None
    db.commit()
    return get_ticket(db, ticket.id) or ticket


def _commit_reload(db: Session, ticket: Ticket) -> Ticket:
    db.commit()
    return get_ticket(db, ticket.id) or ticket


def update_ticket(
    db: Session,
    ticket: Ticket,
    actor: User,
    *,
    title: str,
    description: str,
    lang: str | None = None,
) -> Ticket:
    if not can_edit_ticket(actor, ticket, db):
        raise HTTPException(
            status_code=403,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.no_edit"),
        )
    lang = lang or DEFAULT_LANG
    data = _clean_many_or_400(
        {
            "ticket.title": title,
            "ticket.description": description,
        },
        lang=lang,
    )
    ticket.title = data["ticket.title"]
    ticket.description = data["ticket.description"]
    return _commit_reload(db, ticket)


def set_priority(
    db: Session,
    ticket: Ticket,
    actor: User,
    priority: TicketPriority,
    *,
    lang: str | None = None,
) -> Ticket:
    if not can_edit_ticket(actor, ticket, db):
        raise HTTPException(
            status_code=403,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.no_priority"),
        )
    ticket.priority = priority
    return _commit_reload(db, ticket)


def set_type(
    db: Session,
    ticket: Ticket,
    actor: User,
    ticket_type: TicketType,
    *,
    lang: str | None = None,
) -> Ticket:
    if not can_edit_ticket(actor, ticket, db):
        raise HTTPException(
            status_code=403,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.no_type"),
        )
    if ticket_type == ticket.type:
        return ticket
    ticket.type = ticket_type
    return _commit_reload(db, ticket)


def list_project_tags(db: Session, project_id: int) -> list[Tag]:
    return list(
        db.scalars(
            select(Tag).where(Tag.project_id == project_id).order_by(Tag.name)
        ).all()
    )


def _get_or_create_tag(
    db: Session, project_id: int, name: str, *, lang: str | None = None
) -> Tag:
    lang = lang or DEFAULT_LANG
    cleaned = _clean_or_400("tag.name", name, lang=lang)
    existing = db.scalar(
        select(Tag).where(
            Tag.project_id == project_id,
            func.lower(Tag.name) == cleaned.lower(),
        )
    )
    if existing:
        return existing
    tag = Tag(project_id=project_id, name=cleaned)
    db.add(tag)
    db.flush()
    return tag


def add_ticket_tag(
    db: Session,
    ticket: Ticket,
    actor: User,
    name: str,
    *,
    lang: str | None = None,
) -> Ticket:
    lang = lang or DEFAULT_LANG
    if not can_manage_tags(actor, ticket, db):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.tags_staff_only")
        )
    tag = _get_or_create_tag(db, ticket.project_id, name, lang=lang)
    existing = db.scalar(
        select(TicketTag).where(
            TicketTag.ticket_id == ticket.id, TicketTag.tag_id == tag.id
        )
    )
    if not existing:
        db.add(TicketTag(ticket_id=ticket.id, tag_id=tag.id))
    db.commit()
    return get_ticket(db, ticket.id) or ticket


def remove_ticket_tag(
    db: Session,
    ticket: Ticket,
    actor: User,
    tag_id: int,
    *,
    lang: str | None = None,
) -> Ticket:
    if not can_manage_tags(actor, ticket, db):
        raise HTTPException(
            status_code=403,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.tags_staff_only"),
        )
    row = db.scalar(
        select(TicketTag).where(
            TicketTag.ticket_id == ticket.id, TicketTag.tag_id == tag_id
        )
    )
    if row:
        db.delete(row)
        db.commit()
    return get_ticket(db, ticket.id) or ticket


def add_participant(
    db: Session,
    ticket: Ticket,
    actor: User,
    user_id: int,
    *,
    lang: str | None = None,
) -> Ticket:
    lang = lang or DEFAULT_LANG
    if not actor.is_staff and ticket.author_id != actor.id:
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_add_participant")
        )
    if not is_project_member(db, ticket.project_id, user_id):
        raise HTTPException(
            status_code=400, detail=t(lang, "messages.tickets.user_must_be_member")
        )
    _ensure_participant(db, ticket, user_id)
    db.commit()
    return get_ticket(db, ticket.id) or ticket


def remove_participant(
    db: Session,
    ticket: Ticket,
    actor: User,
    user_id: int | None = None,
    *,
    lang: str | None = None,
) -> Ticket:
    """Participant removes self; admin may remove any participant by user_id."""
    lang = lang or DEFAULT_LANG
    if actor.is_admin:
        if user_id is None:
            raise HTTPException(
                status_code=400, detail=t(lang, "messages.tickets.select_user")
            )
        target_id = user_id
    elif not actor.is_staff and (user_id is None or user_id == actor.id):
        target_id = actor.id
    else:
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_stop_watching")
        )

    row = db.scalar(
        select(TicketParticipant).where(
            TicketParticipant.ticket_id == ticket.id,
            TicketParticipant.user_id == target_id,
        )
    )
    if not row:
        raise HTTPException(
            status_code=400, detail=t(lang, "messages.tickets.not_participant")
        )
    db.delete(row)
    db.commit()
    return get_ticket(db, ticket.id) or ticket


def add_attachment(
    db: Session,
    *,
    file_name: str,
    file_path: str,
    ticket_id: int | None = None,
    comment_id: int | None = None,
    commit: bool = True,
) -> Attachment:
    att = Attachment(
        ticket_id=ticket_id,
        comment_id=comment_id,
        file_name=file_name,
        file_path=file_path,
    )
    db.add(att)
    if commit:
        db.commit()
        db.refresh(att)
    else:
        db.flush()
    return att


def remove_ticket_attachments(
    db: Session,
    ticket: Ticket,
    actor: User,
    attachment_ids: list[int],
    *,
    lang: str | None = None,
) -> Ticket:
    if not can_edit_ticket(actor, ticket, db):
        raise HTTPException(
            status_code=403,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.no_edit"),
        )
    wanted = {int(x) for x in attachment_ids}
    if not wanted:
        return ticket
    for att in list(ticket.attachments):
        if att.id in wanted:
            db.delete(att)
    return _commit_reload(db, ticket)


def remove_comment_attachments(
    db: Session,
    ticket: Ticket,
    comment_id: int,
    actor: User,
    attachment_ids: list[int],
    *,
    lang: str | None = None,
) -> Comment:
    lang = lang or DEFAULT_LANG
    if not can_edit_comments(actor):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_edit_comment")
        )
    comment = _get_ticket_comment(db, ticket, comment_id, lang=lang)
    wanted = {int(x) for x in attachment_ids}
    if not wanted:
        return comment
    for att in list(comment.attachments):
        if att.id in wanted:
            db.delete(att)
    db.commit()
    db.refresh(comment)
    return comment
