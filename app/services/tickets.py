from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

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
from app.services.portal_settings import get_portal_settings
from app.services.projects import (
    can_view_project,
    has_staff_capabilities,
    is_project_member,
    is_project_staff,
    list_project_member_users,
)
from app.utils.i18n import DEFAULT_LANG, t
from app.utils.parse import parse_positive_int
from app.utils.urls import FEED_PER_PAGE_DEFAULT
from app.validation import clean, clean_many

logger = logging.getLogger("pulsedeck.app.tickets")

FEED_PAGE_SIZE_DEFAULT = FEED_PER_PAGE_DEFAULT
FEED_PAGE_SIZES = (10, FEED_PAGE_SIZE_DEFAULT, 50)

_FEED_LIST_LOAD = (
    selectinload(Ticket.author),
    selectinload(Ticket.assignee),
    selectinload(Ticket.project),
    selectinload(Ticket.ticket_tags).selectinload(TicketTag.tag),
)


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


def normalize_feed_page_size(value: int | str | None) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return FEED_PAGE_SIZE_DEFAULT
    return n if n in FEED_PAGE_SIZES else FEED_PAGE_SIZE_DEFAULT


@dataclass(frozen=True)
class TicketListResult:
    items: list[Ticket]
    total: int
    page: int
    page_size: int

    @property
    def last_page(self) -> int:
        return max(1, math.ceil(self.total / self.page_size))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.last_page

    @property
    def range_start(self) -> int:
        return 0 if self.total == 0 else (self.page - 1) * self.page_size + 1

    @property
    def range_end(self) -> int:
        return min(self.page * self.page_size, self.total)


@dataclass(frozen=True)
class TicketPermissions:
    can_assign: bool
    can_set_done: bool
    can_reopen: bool
    can_edit: bool
    can_manage_tags: bool
    can_comment: bool
    can_delete_comments: bool
    can_delete_ticket: bool
    is_project_staff: bool
    can_add_participant: bool


def _is_member(db: Session, user: User, ticket: Ticket, member: bool | None) -> bool:
    if member is not None:
        return member
    return is_project_member(db, ticket.project_id, user.id)


def can_moderate(user: User) -> bool:
    return user.is_admin


def ticket_involved_user_ids(ticket: Ticket) -> set[int]:
    ids = {ticket.author_id}
    if ticket.assignee_id is not None:
        ids.add(ticket.assignee_id)
    for participant in ticket.participants or []:
        ids.add(participant.user_id)
    return ids


def is_ticket_involved(user: User, ticket: Ticket) -> bool:
    return user.id in ticket_involved_user_ids(ticket)


def lock_author_edits(ticket: Ticket) -> None:
    if ticket.author_edits_locked_at is None:
        ticket.author_edits_locked_at = datetime.now(timezone.utc)


def author_edits_locked(ticket: Ticket) -> bool:
    return ticket.author_edits_locked_at is not None


def _is_latest_comment(db: Session, ticket: Ticket, comment: Comment) -> bool:
    latest_id = db.scalar(
        select(Comment.id)
        .where(Comment.ticket_id == ticket.id)
        .order_by(Comment.created_at.desc(), Comment.id.desc())
        .limit(1)
    )
    return latest_id == comment.id


def can_grace_edit_ticket(
    db: Session, user: User, ticket: Ticket, *, member: bool | None = None
) -> bool:
    if ticket.deleted_at is not None:
        return False
    if not _is_member(db, user, ticket, member):
        return False
    if ticket.author_id != user.id:
        return False
    return not author_edits_locked(ticket)


def can_grace_edit_comment(
    db: Session, user: User, ticket: Ticket, comment: Comment
) -> bool:
    if ticket.deleted_at is not None:
        return False
    if not is_project_member(db, ticket.project_id, user.id):
        return False
    if comment.author_id != user.id:
        return False
    if author_edits_locked(ticket):
        return False
    return _is_latest_comment(db, ticket, comment)


def can_edit_ticket(
    user: User, ticket: Ticket, db: Session, *, member: bool | None = None
) -> bool:
    if can_moderate(user):
        return True
    if ticket.deleted_at is not None:
        return False
    return can_grace_edit_ticket(db, user, ticket, member=member)


def can_edit_comment(db: Session, user: User, ticket: Ticket, comment: Comment) -> bool:
    if can_moderate(user):
        return True
    if ticket.deleted_at is not None:
        return False
    return can_grace_edit_comment(db, user, ticket, comment)


def can_delete_ticket(user: User, ticket: Ticket | None = None) -> bool:
    if ticket is not None and ticket.deleted_at is not None:
        return False
    return can_moderate(user)


def can_comment(
    db: Session, user: User, ticket: Ticket, *, member: bool | None = None
) -> bool:
    if can_moderate(user):
        return ticket.deleted_at is None
    if ticket.deleted_at is not None or ticket.status == TicketStatus.DONE:
        return False
    if not _is_member(db, user, ticket, member):
        return False
    if has_staff_capabilities(db, ticket.project_id, user):
        return True
    if ticket.author_id == user.id:
        return True
    return any(p.user_id == user.id for p in (ticket.participants or []))


def can_assign(user: User, ticket: Ticket, db: Session) -> bool:
    return ticket.deleted_at is None and has_staff_capabilities(
        db, ticket.project_id, user
    )


def can_set_done(
    user: User, ticket: Ticket, db: Session, *, member: bool | None = None
) -> bool:
    if can_moderate(user):
        return ticket.deleted_at is None
    if ticket.deleted_at is not None:
        return False
    if not _is_member(db, user, ticket, member):
        return False
    if has_staff_capabilities(db, ticket.project_id, user):
        return True
    return ticket.author_id == user.id


def can_reopen(
    user: User, ticket: Ticket, db: Session, *, member: bool | None = None
) -> bool:
    if can_moderate(user):
        return ticket.deleted_at is None and ticket.status == TicketStatus.DONE
    if ticket.deleted_at is not None or ticket.status != TicketStatus.DONE:
        return False
    if not _is_member(db, user, ticket, member):
        return False
    if has_staff_capabilities(db, ticket.project_id, user):
        return True
    if ticket.closed_at is None:
        return False
    portal = get_portal_settings(db)
    closed = ticket.closed_at
    if closed.tzinfo is None:
        closed = closed.replace(tzinfo=timezone.utc)
    deadline = closed + timedelta(days=portal.ticket_reopen_days)
    return datetime.now(timezone.utc) <= deadline


def can_manage_workflow(user: User, ticket: Ticket, db: Session) -> bool:
    return ticket.deleted_at is None and has_staff_capabilities(
        db, ticket.project_id, user
    )


def can_manage_tags(user: User, ticket: Ticket, db: Session) -> bool:
    return can_manage_workflow(user, ticket, db)


def _participant_exclude_ids(ticket: Ticket) -> set[int]:
    ids = {ticket.author_id}
    if ticket.assignee_id is not None:
        ids.add(ticket.assignee_id)
    for participant in ticket.participants or []:
        ids.add(participant.user_id)
    return ids


def user_display_key(user: User) -> str:
    return (user.display_name or "").casefold()


def _participant_row(
    db: Session, ticket: Ticket, user_id: int
) -> TicketParticipant | None:
    return db.scalar(
        select(TicketParticipant).where(
            TicketParticipant.ticket_id == ticket.id,
            TicketParticipant.user_id == user_id,
        )
    )


def list_visible_participants(ticket: Ticket) -> list[TicketParticipant]:
    assignee_id = ticket.assignee_id
    rows = [
        participant
        for participant in (ticket.participants or [])
        if participant.user_id != assignee_id
    ]
    return sorted(
        rows,
        key=lambda participant: (
            user_display_key(participant.user) if participant.user else ""
        ),
    )


def _is_project_client(db: Session, project_id: int, user: User) -> bool:
    return (
        user.is_active
        and is_project_member(db, project_id, user.id)
        and not is_project_staff(db, project_id, user)
    )


def _client_author_can_add(db: Session, ticket: Ticket, actor: User) -> bool:
    return ticket.author_id == actor.id and _is_project_client(
        db, ticket.project_id, actor
    )


def can_add_participant(db: Session, actor: User, ticket: Ticket) -> bool:
    return is_project_staff(db, ticket.project_id, actor) or _client_author_can_add(
        db, ticket, actor
    )


def _addable_participant_candidates(
    db: Session, ticket: Ticket, actor: User
) -> list[User]:
    members = list_project_member_users(db, ticket.project)
    if is_project_staff(db, ticket.project_id, actor):
        return members
    if _client_author_can_add(db, ticket, actor):
        return [
            user for user in members if _is_project_client(db, ticket.project_id, user)
        ]
    return []


def can_add_as_participant(
    db: Session,
    ticket: Ticket,
    actor: User,
    target: User,
) -> bool:
    if target.id in _participant_exclude_ids(ticket) or not target.is_active:
        return False
    if is_project_staff(db, ticket.project_id, actor):
        return is_project_member(db, ticket.project_id, target.id)
    if _client_author_can_add(db, ticket, actor):
        return _is_project_client(db, ticket.project_id, target)
    return False


def list_addable_participants(
    db: Session,
    ticket: Ticket,
    actor: User,
) -> list[User]:
    excluded = _participant_exclude_ids(ticket)
    return sorted(
        [
            user
            for user in _addable_participant_candidates(db, ticket, actor)
            if user.id not in excluded
        ],
        key=user_display_key,
    )


def sorted_project_members(db: Session, project: Project) -> list[User]:
    return sorted(
        list_project_member_users(db, project),
        key=user_display_key,
    )


def can_view_ticket(db: Session, user: User, ticket: Ticket) -> bool:
    if ticket.deleted_at is not None:
        return can_moderate(user)
    return can_moderate(user) or is_project_member(db, ticket.project_id, user.id)


def get_ticket_permissions(
    db: Session, user: User, ticket: Ticket
) -> TicketPermissions:
    member = is_project_member(db, ticket.project_id, user.id)
    staff_ui = has_staff_capabilities(db, ticket.project_id, user)
    return TicketPermissions(
        can_assign=can_assign(user, ticket, db),
        can_set_done=can_set_done(user, ticket, db, member=member),
        can_reopen=can_reopen(user, ticket, db, member=member),
        can_edit=can_edit_ticket(user, ticket, db, member=member),
        can_manage_tags=can_manage_tags(user, ticket, db),
        can_comment=can_comment(db, user, ticket, member=member),
        can_delete_comments=can_moderate(user),
        can_delete_ticket=can_delete_ticket(user, ticket),
        is_project_staff=staff_ui,
        can_add_participant=can_add_participant(db, user, ticket),
    )


def require_project_access(
    db: Session, user: User, project_id: int, *, lang: str | None = None
) -> None:
    if not can_view_project(db, user, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.no_project_access"),
        )


def require_project_membership(
    db: Session, user: User, project_id: int, *, lang: str | None = None
) -> None:
    if can_moderate(user):
        return
    if not is_project_member(db, project_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t(lang or DEFAULT_LANG, "messages.tickets.no_project_access"),
        )


def _apply_view_filter(stmt, *, view: str | None):
    if not view or view == "all":
        return stmt
    if view == "open":
        return stmt.where(Ticket.status.in_(_OPEN_STATUSES))
    if view == "needs_us":
        return stmt.where(Ticket.status.in_(_NEEDS_US_STATUSES))
    if view == "unassigned":
        return stmt.where(Ticket.assignee_id.is_(None))
    if view in ("waiting_on_client", "waiting_on_me"):
        return stmt.where(Ticket.status == TicketStatus.WAITING_ON_CLIENT)
    if view == "done":
        return stmt.where(Ticket.status == TicketStatus.DONE)
    return stmt


def _apply_mine_scope(stmt, user: User, *, project_id: int, db: Session):
    if is_project_staff(db, project_id, user):
        return stmt.where(
            or_(Ticket.assignee_id == user.id, Ticket.author_id == user.id)
        )
    participant_exists = (
        select(TicketParticipant.ticket_id)
        .where(
            TicketParticipant.ticket_id == Ticket.id,
            TicketParticipant.user_id == user.id,
        )
        .exists()
    )
    return stmt.where(or_(Ticket.author_id == user.id, participant_exists))


def _apply_sort(stmt, sort: str | None):
    if sort == "created_at":
        return stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc())
    if sort == "priority":
        priority_order = case(
            (Ticket.priority == TicketPriority.HIGH, 0),
            (Ticket.priority == TicketPriority.NORMAL, 1),
            else_=2,
        )
        return stmt.add_columns(priority_order).order_by(
            priority_order, Ticket.updated_at.desc(), Ticket.id.desc()
        )
    return stmt.order_by(Ticket.updated_at.desc(), Ticket.id.desc())


def _build_feed_query(
    db: Session,
    project_id: int,
    *,
    user: User,
    view: str | None = None,
    mine: bool = False,
    priority_filter: str | None = None,
    type_filter: str | None = None,
    status_filter: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    include_deleted: bool = False,
) -> Select[tuple[Ticket]]:
    stmt = select(Ticket).where(Ticket.project_id == project_id)
    if not include_deleted:
        stmt = stmt.where(Ticket.deleted_at.is_(None))
    stmt = _apply_view_filter(stmt, view=None if q else view)
    if mine:
        stmt = _apply_mine_scope(stmt, user, project_id=project_id, db=db)
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
    if status_filter:
        try:
            stmt = stmt.where(Ticket.status == TicketStatus(status_filter))
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
            pattern = f"%{raw}%"
            author_match = (
                select(User.id)
                .where(
                    User.id == Ticket.author_id,
                    func.concat(User.first_name, " ", User.last_name).ilike(pattern),
                )
                .exists()
            )
            matches = [
                Ticket.title.ilike(pattern),
                author_match,
            ]
            ref = re.fullmatch(r"(?:[A-Za-z0-9]{1,5}-)?(\d+)", raw, flags=re.IGNORECASE)
            if ref:
                matches.append(Ticket.number == int(ref.group(1)))
            stmt = stmt.where(or_(*matches))
    return stmt.distinct()


def list_tickets(
    db: Session,
    project_id: int,
    *,
    user: User,
    view: str | None = None,
    mine: bool = False,
    priority_filter: str | None = None,
    type_filter: str | None = None,
    status_filter: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    page: int = 1,
    page_size: int = FEED_PAGE_SIZE_DEFAULT,
) -> TicketListResult:
    if status_filter:
        view = None
    elif view and view != "all":
        status_filter = None
    page_size = normalize_feed_page_size(page_size)
    base_stmt = _build_feed_query(
        db,
        project_id,
        user=user,
        view=view,
        mine=mine,
        priority_filter=priority_filter,
        type_filter=type_filter,
        status_filter=status_filter,
        tag=tag,
        q=q,
        include_deleted=can_moderate(user),
    )
    total = (
        db.scalar(
            select(func.count()).select_from(
                base_stmt.with_only_columns(Ticket.id).subquery()
            )
        )
        or 0
    )
    page = min(parse_positive_int(page), max(1, math.ceil(total / page_size)))
    items = list(
        db.scalars(
            _apply_sort(base_stmt.options(*_FEED_LIST_LOAD), sort)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return TicketListResult(items=items, total=total, page=page, page_size=page_size)


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
    if ticket.author_id == user_id or ticket.assignee_id == user_id:
        return
    if _participant_row(db, ticket, user_id):
        return
    db.add(TicketParticipant(ticket_id=ticket.id, user_id=user_id))


def _drop_participant(db: Session, ticket: Ticket, user_id: int) -> None:
    row = _participant_row(db, ticket, user_id)
    if row:
        db.delete(row)


def _sync_participant_watch(db: Session, ticket: Ticket, user_id: int) -> None:
    _ensure_participant(db, ticket, user_id)
    if ticket.assignee_id == user_id:
        _drop_participant(db, ticket, user_id)


def latest_visible_comment_id(db: Session, ticket: Ticket, user: User) -> int:
    q = select(func.max(Comment.id)).where(Comment.ticket_id == ticket.id)
    if not has_staff_capabilities(db, ticket.project_id, user):
        q = q.where(Comment.is_internal.is_(False))
    return int(db.scalar(q) or 0)


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
    if is_internal and not has_staff_capabilities(db, ticket.project_id, author):
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
    lock_author_edits(ticket)
    staff = has_staff_capabilities(db, ticket.project_id, author)
    if not is_internal:
        if staff:
            ticket.status = TicketStatus.WAITING_ON_CLIENT
            if ticket.assignee_id is None:
                ticket.assignee_id = author.id
        else:
            ticket.status = TicketStatus.IN_PROGRESS
    _sync_participant_watch(db, ticket, author.id)
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


def get_ticket_comment(
    db: Session, ticket: Ticket, comment_id: int, *, lang: str | None = None
) -> Comment:
    return _get_ticket_comment(db, ticket, comment_id, lang=lang or DEFAULT_LANG)


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
    comment = _get_ticket_comment(db, ticket, comment_id, lang=lang)
    if not can_edit_comment(db, actor, ticket, comment):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_edit_comment")
        )
    text = _clean_or_400("comment.content", content, lang=lang)
    comment.content = text
    comment.edited_at = datetime.now(timezone.utc)
    comment.edited_by_id = actor.id
    if can_moderate(actor):
        logger.info(
            "Moderation edit comment id=%s ticket_id=%s by user_id=%s",
            comment.id,
            ticket.id,
            actor.id,
        )
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
    if not can_moderate(actor):
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
    previous_id = ticket.assignee_id
    if assignee_id is not None:
        assignee = db.get(User, assignee_id)
        if not assignee or not is_project_staff(db, ticket.project_id, assignee):
            raise HTTPException(
                status_code=400,
                detail=t(lang, "messages.tickets.assignee_must_be_staff"),
            )
        if previous_id == assignee.id:
            return get_ticket(db, ticket.id) or ticket
        ticket.assignee_id = assignee.id
        _drop_participant(db, ticket, assignee.id)
        lock_author_edits(ticket)
        if ticket.status == TicketStatus.NEW:
            ticket.status = TicketStatus.IN_PROGRESS
    else:
        if previous_id is None:
            return get_ticket(db, ticket.id) or ticket
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
    if not can_moderate(actor) and not is_project_member(
        db, ticket.project_id, actor.id
    ):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_project_access")
        )

    if status_value == ticket.status:
        return ticket

    if has_staff_capabilities(db, ticket.project_id, actor):
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
    if can_moderate(actor) and not can_grace_edit_ticket(db, actor, ticket):
        logger.info("Moderation edit ticket id=%s by user_id=%s", ticket.id, actor.id)
    return _commit_reload(db, ticket)


def set_priority(
    db: Session,
    ticket: Ticket,
    actor: User,
    priority: TicketPriority,
    *,
    lang: str | None = None,
) -> Ticket:
    if not can_manage_workflow(actor, ticket, db):
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
    if not can_manage_workflow(actor, ticket, db):
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
    if not can_add_participant(db, actor, ticket):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_add_participant")
        )
    target = db.get(User, user_id)
    if not target or not can_add_as_participant(db, ticket, actor, target):
        detail = (
            t(lang, "messages.tickets.user_must_be_member")
            if is_project_staff(db, ticket.project_id, actor)
            else t(lang, "messages.tickets.participant_not_allowed")
        )
        raise HTTPException(status_code=400, detail=detail)
    _ensure_participant(db, ticket, user_id)
    db.commit()
    return get_ticket(db, ticket.id) or ticket


def is_ticket_watcher(ticket: Ticket, user_id: int) -> bool:
    if user_id in (ticket.author_id, ticket.assignee_id):
        return False
    return any(p.user_id == user_id for p in (ticket.participants or []))


def unwatch_ticket(db: Session, user_id: int, ticket_id: int) -> bool:
    ticket = get_ticket(db, ticket_id)
    if ticket is None:
        return False
    row = _participant_row(db, ticket, user_id)
    if row:
        db.delete(row)
        db.commit()
    return True


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
    if can_moderate(actor):
        if user_id is None:
            raise HTTPException(
                status_code=400, detail=t(lang, "messages.tickets.select_user")
            )
        target_id = user_id
    elif not is_project_staff(db, ticket.project_id, actor) and (
        user_id is None or user_id == actor.id
    ):
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


def soft_delete_ticket(
    db: Session,
    ticket: Ticket,
    actor: User,
    *,
    lang: str | None = None,
) -> Ticket:
    lang = lang or DEFAULT_LANG
    if not can_delete_ticket(actor, ticket):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_delete")
        )
    if ticket.deleted_at is None:
        ticket.deleted_at = datetime.now(timezone.utc)
        ticket.deleted_by_id = actor.id
        logger.info("Soft-delete ticket id=%s by user_id=%s", ticket.id, actor.id)
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
    comment = _get_ticket_comment(db, ticket, comment_id, lang=lang)
    if not can_edit_comment(db, actor, ticket, comment):
        raise HTTPException(
            status_code=403, detail=t(lang, "messages.tickets.no_edit_comment")
        )
    wanted = {int(x) for x in attachment_ids}
    if not wanted:
        return comment
    for att in list(comment.attachments or []):
        if att.id in wanted:
            db.delete(att)
    db.commit()
    db.refresh(comment)
    return comment
