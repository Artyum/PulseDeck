from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.email_outbox import EmailOutbox
from app.models.enums import EmailOutboxStatus, TicketStatus, TicketType, UserRole
from app.models.ticket import Comment, Tag, Ticket, TicketTag
from app.models.user import Project, ProjectMember, User
from app.utils.i18n import DEFAULT_LANG, t
from app.validation import clean, clean_many

_E = TypeVar("_E", bound=Enum)


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    project: Project
    member_count: int
    ticket_count: int
    tags: tuple[Tag, ...] = ()


@dataclass(frozen=True, slots=True)
class AdminDashboardStats:
    projects: int
    users: int
    open_tickets: int
    messages: int
    pending_users: int
    emails_sent: int


@dataclass(frozen=True, slots=True)
class AdminProjectStats:
    members: int
    open_tickets: int
    tickets: int
    messages: int
    status_counts: dict[TicketStatus, int]
    type_counts: dict[TicketType, int]


@dataclass(frozen=True, slots=True)
class AdminProjectUserActivity:
    user: User
    tickets_created: int


def list_projects(
    db: Session, *, active_only: bool = False, inactive_only: bool = False
) -> list[Project]:
    stmt = select(Project)
    if active_only:
        stmt = stmt.where(Project.is_active.is_(True))
    elif inactive_only:
        stmt = stmt.where(Project.is_active.is_(False))
    return list(db.scalars(stmt.order_by(Project.name)).all())


def admin_dashboard_stats(db: Session) -> AdminDashboardStats:
    def _count(stmt) -> int:
        return int(db.scalar(stmt) or 0)

    return AdminDashboardStats(
        projects=_count(select(func.count()).select_from(Project)),
        users=_count(select(func.count()).select_from(User)),
        open_tickets=_count(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.status != TicketStatus.DONE)
        ),
        messages=_count(select(func.count()).select_from(Comment)),
        pending_users=_count(
            select(func.count())
            .select_from(User)
            .where(User.activated_at.is_(None), User.is_active.is_(True))
        ),
        emails_sent=_count(
            select(func.count())
            .select_from(EmailOutbox)
            .where(EmailOutbox.status == EmailOutboxStatus.SENT)
        ),
    )


def _ticket_enum_counts(
    db: Session,
    project_id: int,
    column,
    enum_cls: type[_E],
) -> dict[_E, int]:
    counts: dict[_E, int] = {member: 0 for member in enum_cls}
    for raw, count in db.execute(
        select(column, func.count())
        .where(Ticket.project_id == project_id)
        .group_by(column)
    ):
        key = raw if isinstance(raw, enum_cls) else enum_cls(raw)
        counts[key] = int(count)
    return counts


def admin_project_stats(
    db: Session,
    project_id: int,
    *,
    sort: str | None = None,
    sort_dir: str | None = None,
) -> tuple[AdminProjectStats, list[AdminProjectUserActivity]] | None:
    if db.get(Project, project_id) is None:
        return None

    def _count(stmt) -> int:
        return int(db.scalar(stmt) or 0)

    members = list(
        db.scalars(
            select(User)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.last_name, User.first_name)
        ).all()
    )
    ticket_counts = {
        int(user_id): int(count)
        for user_id, count in db.execute(
            select(Ticket.author_id, func.count())
            .where(Ticket.project_id == project_id)
            .group_by(Ticket.author_id)
        )
    }
    stats = AdminProjectStats(
        members=len(members),
        open_tickets=_count(
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.project_id == project_id,
                Ticket.status != TicketStatus.DONE,
            )
        ),
        tickets=_count(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.project_id == project_id)
        ),
        messages=_count(
            select(func.count())
            .select_from(Comment)
            .join(Ticket, Ticket.id == Comment.ticket_id)
            .where(Ticket.project_id == project_id)
        ),
        status_counts=_ticket_enum_counts(db, project_id, Ticket.status, TicketStatus),
        type_counts=_ticket_enum_counts(db, project_id, Ticket.type, TicketType),
    )
    activity = [
        AdminProjectUserActivity(
            user=member,
            tickets_created=ticket_counts.get(member.id, 0),
        )
        for member in members
    ]
    descending = (sort_dir or "").strip().lower() == "desc"
    col = (sort or "").strip().lower()

    def _activity_key(row: AdminProjectUserActivity):
        name = (
            (row.user.last_name or "").casefold(),
            (row.user.first_name or "").casefold(),
            row.user.id,
        )
        if col == "role":
            return (row.user.role, *name)
        if col == "tickets":
            return (row.tickets_created, *name)
        if col == "last_login":
            ts = row.user.last_login_at
            return (ts.timestamp() if ts is not None else 0.0, *name)
        return name

    activity.sort(key=_activity_key, reverse=descending)
    return stats, activity


def list_users(
    db: Session,
    *,
    role: UserRole | None = None,
    project_id: int | None = None,
    q: str | None = None,
    status: str | None = None,
    sort: str | None = None,
    sort_dir: str | None = None,
    lang: str | None = None,
) -> list[User]:
    lang = lang or DEFAULT_LANG
    stmt = select(User).options(selectinload(User.memberships))
    status_key = (status or "").strip().lower()
    if status_key == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status_key == "blocked":
        stmt = stmt.where(User.is_active.is_(False))
    elif status_key == "pending":
        stmt = stmt.where(User.activated_at.is_(None))
    if role is not None:
        stmt = stmt.where(User.role == role)
    if project_id is not None:
        stmt = stmt.where(
            User.id.in_(
                select(ProjectMember.user_id).where(
                    ProjectMember.project_id == project_id
                )
            )
        )
    raw = clean("search.q", q or "", lang=lang)
    if raw:
        pattern = f"%{raw}%"
        full_name = func.concat(User.first_name, " ", User.last_name)
        stmt = stmt.where(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                full_name.ilike(pattern),
                User.email.ilike(pattern),
                User.phone.ilike(pattern),
            )
        )
    descending = (sort_dir or "").strip().lower() == "desc"
    col = (sort or "").strip().lower()
    if col == "email":
        primary = User.email.desc() if descending else User.email.asc()
        stmt = stmt.order_by(primary, User.id)
    elif col == "phone":
        primary = User.phone.desc() if descending else User.phone.asc()
        stmt = stmt.order_by(primary.nulls_last(), User.id)
    elif col == "role":
        primary = User.role.desc() if descending else User.role.asc()
        stmt = stmt.order_by(
            primary, User.first_name.asc(), User.last_name.asc(), User.id
        )
    elif col == "status":
        primary = User.is_active.desc() if descending else User.is_active.asc()
        stmt = stmt.order_by(
            primary, User.first_name.asc(), User.last_name.asc(), User.id
        )
    else:
        first = User.first_name.desc() if descending else User.first_name.asc()
        last = User.last_name.desc() if descending else User.last_name.asc()
        stmt = stmt.order_by(first, last, User.id)
    return list(db.scalars(stmt).all())


def list_project_summaries(
    db: Session, *, disabled_only: bool = False
) -> list[ProjectSummary]:
    projects = list_projects(
        db, active_only=not disabled_only, inactive_only=disabled_only
    )
    if not projects:
        return []
    ids = [p.id for p in projects]
    member_counts: dict[int, int] = {
        int(project_id): int(count)
        for project_id, count in db.execute(
            select(ProjectMember.project_id, func.count())
            .where(ProjectMember.project_id.in_(ids))
            .group_by(ProjectMember.project_id)
        ).all()
    }
    ticket_counts: dict[int, int] = {
        int(project_id): int(count)
        for project_id, count in db.execute(
            select(Ticket.project_id, func.count())
            .where(Ticket.project_id.in_(ids))
            .group_by(Ticket.project_id)
        ).all()
    }
    tags_by_project = list_project_tags_for_projects(db, ids)
    return [
        ProjectSummary(
            project=p,
            member_count=member_counts.get(p.id, 0),
            ticket_count=ticket_counts.get(p.id, 0),
            tags=tuple(tags_by_project.get(p.id, [])),
        )
        for p in projects
    ]


def can_view_project(db: Session, user: User, project_id: int) -> bool:
    if user.is_admin:
        return db.get(Project, project_id) is not None
    return is_project_member(db, project_id, user.id)


def user_has_staff_ops(user: User) -> bool:
    return user.role in (UserRole.STAFF, UserRole.ADMIN)


def is_project_staff(db: Session, project_id: int, user: User) -> bool:
    if not user.is_active or not user_has_staff_ops(user):
        return False
    return is_project_member(db, project_id, user.id)


def has_staff_capabilities(db: Session, project_id: int, user: User) -> bool:
    return user.is_admin or is_project_staff(db, project_id, user)


def list_project_staff(db: Session, project_id: int) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(
                ProjectMember.project_id == project_id,
                User.is_active.is_(True),
                User.role.in_((UserRole.STAFF, UserRole.ADMIN)),
            )
            .order_by(User.last_name, User.first_name)
        ).all()
    )


def list_project_clients(db: Session, project_id: int) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(
                ProjectMember.project_id == project_id,
                User.is_active.is_(True),
                User.role == UserRole.USER,
            )
            .order_by(User.last_name, User.first_name)
        ).all()
    )


def count_active_project_staff(db: Session, project_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(
                ProjectMember.project_id == project_id,
                User.is_active.is_(True),
                User.role.in_((UserRole.STAFF, UserRole.ADMIN)),
            )
        )
        or 0
    )


def would_leave_project_without_staff(
    db: Session,
    project_id: int,
    *,
    excluding_user_id: int | None = None,
) -> bool:
    project = db.get(Project, project_id)
    if not project or not project.is_active:
        return False
    remaining = count_active_project_staff(db, project_id)
    if excluding_user_id is None:
        return remaining < 1
    user = db.get(User, excluding_user_id)
    if (
        user
        and user.is_active
        and user_has_staff_ops(user)
        and is_project_member(db, project_id, excluding_user_id)
    ):
        remaining -= 1
    return remaining < 1


def list_user_projects(db: Session, user: User) -> list[Project]:
    if user.is_admin:
        return list_projects(db, active_only=True)
    return list(
        db.scalars(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                ProjectMember.user_id == user.id,
                Project.is_active.is_(True),
            )
            .order_by(Project.name)
        ).all()
    )


def list_used_project_tags(db: Session, project_id: int) -> list[Tag]:
    return list(
        db.scalars(
            select(Tag)
            .distinct()
            .join(TicketTag, TicketTag.tag_id == Tag.id)
            .join(Ticket, Ticket.id == TicketTag.ticket_id)
            .where(Tag.project_id == project_id)
            .order_by(Tag.name)
        ).all()
    )


def list_project_tags_for_projects(
    db: Session, project_ids: list[int]
) -> dict[int, list[Tag]]:
    if not project_ids:
        return {}
    rows = db.scalars(
        select(Tag)
        .join(TicketTag, TicketTag.tag_id == Tag.id)
        .where(Tag.project_id.in_(project_ids))
        .distinct()
        .order_by(Tag.name)
    ).all()
    result: dict[int, list[Tag]] = {pid: [] for pid in project_ids}
    for tag in rows:
        result[tag.project_id].append(tag)
    return result


def list_project_member_users(
    db: Session,
    project: Project,
    *,
    include_admins: bool = True,
    sort: str | None = None,
    sort_dir: str | None = None,
) -> list[User]:
    members = [m.user for m in project.members if m.user]
    if not include_admins:
        members = [u for u in members if not u.is_admin]
    descending = (sort_dir or "").strip().lower() == "desc"
    col = (sort or "").strip().lower()

    def _member_key(user: User):
        name = (
            (user.last_name or "").casefold(),
            (user.first_name or "").casefold(),
            user.id,
        )
        if col == "role":
            return (user.role, *name)
        return name

    members.sort(key=_member_key, reverse=descending)
    return members


def list_addable_users(db: Session, project: Project) -> list[User]:
    member_ids = {m.user_id for m in project.members}
    return [u for u in list_users(db) if u.id not in member_ids]


def list_staff_candidates(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.role.in_((UserRole.STAFF, UserRole.ADMIN)),
            )
            .order_by(User.last_name, User.first_name)
        ).all()
    )


def get_project_by_key(db: Session, key: str) -> Project | None:
    normalized = (key or "").strip().upper()
    return db.scalar(
        select(Project)
        .where(Project.key == normalized)
        .options(selectinload(Project.members).selectinload(ProjectMember.user))
    )


def get_project_by_key_or_404(
    db: Session,
    key: str,
    *,
    lang: str | None = None,
    require_active: bool = False,
) -> Project:
    project = get_project_by_key(db, key)
    if not project or (require_active and not project.is_active):
        raise HTTPException(
            status_code=404, detail=t(lang or DEFAULT_LANG, "messages.http.not_found")
        )
    return project


def _name_taken(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(Project.id).where(func.lower(Project.name) == name.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(Project.id != exclude_id)
    return db.scalar(stmt) is not None


def _key_taken(db: Session, key: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(Project.id).where(Project.key == key)
    if exclude_id is not None:
        stmt = stmt.where(Project.id != exclude_id)
    return db.scalar(stmt) is not None


def _normalize_project_fields(
    db: Session,
    name: str,
    key: str,
    description: str | None,
    *,
    exclude_id: int | None = None,
    lang: str,
) -> tuple[str, str, str | None]:
    data = clean_many(
        {
            "project.name": name,
            "project.key": key,
            "project.description": description or "",
        },
        lang=lang,
    )
    clean_name = data["project.name"]
    clean_key = data["project.key"]
    clean_description = data["project.description"]
    if _name_taken(db, clean_name, exclude_id=exclude_id):
        raise ValueError(t(lang, "messages.projects.name_exists"))
    if _key_taken(db, clean_key, exclude_id=exclude_id):
        raise ValueError(t(lang, "messages.projects.key_exists"))
    return clean_name, clean_key, clean_description


def create_project(
    db: Session,
    name: str,
    key: str,
    description: str | None = None,
    *,
    initial_staff_ids: list[int] | None = None,
    lang: str | None = None,
) -> Project:
    lang = lang or DEFAULT_LANG
    clean_name, clean_key, clean_description = _normalize_project_fields(
        db, name, key, description, lang=lang
    )
    staff_ids = list(dict.fromkeys(int(x) for x in (initial_staff_ids or [])))
    if not staff_ids:
        raise ValueError(t(lang, "messages.projects.staff_required"))
    staff_users: list[User] = []
    for uid in staff_ids:
        user = db.get(User, uid)
        if not user or not user.is_active or not user_has_staff_ops(user):
            raise ValueError(t(lang, "messages.projects.staff_invalid"))
        staff_users.append(user)
    project = Project(
        name=clean_name,
        key=clean_key,
        description=clean_description,
    )
    db.add(project)
    db.flush()
    for user in staff_users:
        db.add(ProjectMember(project_id=project.id, user_id=user.id))
    db.commit()
    db.refresh(project)
    return project


def update_project(
    db: Session,
    project: Project,
    *,
    name: str,
    key: str,
    description: str | None = None,
    notify_clients_on_staff_ticket: bool | None = None,
    lang: str | None = None,
) -> Project:
    clean_name, clean_key, clean_description = _normalize_project_fields(
        db, name, key, description, exclude_id=project.id, lang=lang or DEFAULT_LANG
    )
    project.name = clean_name
    project.key = clean_key
    project.description = clean_description
    if notify_clients_on_staff_ticket is not None:
        project.notify_clients_on_staff_ticket = notify_clients_on_staff_ticket
    db.commit()
    db.refresh(project)
    return project


def set_project_notify_clients_on_staff_ticket(
    db: Session,
    project: Project,
    *,
    enabled: bool,
) -> Project:
    project.notify_clients_on_staff_ticket = enabled
    db.commit()
    db.refresh(project)
    return project


def set_project_active(db: Session, project: Project, *, active: bool) -> Project:
    project.is_active = active
    db.commit()
    db.refresh(project)
    return project


def _membership_row(db: Session, project_id: int, user_id: int) -> ProjectMember | None:
    return db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )


def is_project_member(db: Session, project_id: int, user_id: int) -> bool:
    return _membership_row(db, project_id, user_id) is not None


def add_project_member(
    db: Session,
    project_id: int,
    user_id: int,
    *,
    lang: str | None = None,
) -> None:
    lang = lang or DEFAULT_LANG
    user = db.get(User, user_id)
    if not user:
        return
    if _membership_row(db, project_id, user_id) is not None:
        return
    db.add(ProjectMember(project_id=project_id, user_id=user_id))
    db.commit()


def remove_project_member(
    db: Session,
    project_id: int,
    user_id: int,
    *,
    lang: str | None = None,
) -> None:
    lang = lang or DEFAULT_LANG
    row = _membership_row(db, project_id, user_id)
    if not row:
        return
    if would_leave_project_without_staff(db, project_id, excluding_user_id=user_id):
        raise ValueError(t(lang, "messages.projects.last_staff"))
    db.delete(row)
    db.commit()


def resolve_project_ids(
    db: Session, project_ids: list[int], *, lang: str | None = None
) -> list[int]:
    lang = lang or DEFAULT_LANG
    unique = list(dict.fromkeys(int(x) for x in project_ids))
    if not unique:
        raise ValueError(t(lang, "messages.projects.at_least_one"))
    found = set(db.scalars(select(Project.id).where(Project.id.in_(unique))).all())
    if found != set(unique):
        raise ValueError(t(lang, "messages.projects.invalid"))
    return unique


def set_user_projects(
    db: Session, user_id: int, project_ids: list[int], *, lang: str | None = None
) -> None:
    lang = lang or DEFAULT_LANG
    user = db.get(User, user_id)
    current = list(
        db.scalars(select(ProjectMember).where(ProjectMember.user_id == user_id)).all()
    )
    current_ids = {m.project_id for m in current}
    inactive_ids = set(
        db.scalars(
            select(Project.id).where(
                Project.id.in_(tuple(current_ids) or (0,)),
                Project.is_active.is_(False),
            )
        ).all()
    )
    wanted = inactive_ids | (
        set(resolve_project_ids(db, project_ids, lang=lang)) if project_ids else set()
    )
    if not wanted and not (user and user.is_admin):
        raise ValueError(t(lang, "messages.projects.at_least_one"))
    for row in current:
        if row.project_id not in wanted:
            if would_leave_project_without_staff(
                db, row.project_id, excluding_user_id=user_id
            ):
                raise ValueError(t(lang, "messages.projects.last_staff"))
            db.delete(row)
    for pid in wanted - current_ids:
        db.add(ProjectMember(project_id=pid, user_id=user_id))
    db.flush()
