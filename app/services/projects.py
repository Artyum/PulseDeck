from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import UserRole
from app.models.ticket import Tag, Ticket, TicketTag
from app.models.user import Project, ProjectMember, User
from app.utils.i18n import DEFAULT_LANG, t
from app.utils.project_key import validate_project_key


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    project: Project
    member_count: int
    ticket_count: int
    tags: tuple[Tag, ...] = ()


def list_projects(db: Session, *, active_only: bool = False) -> list[Project]:
    stmt = select(Project)
    if active_only:
        stmt = stmt.where(Project.is_active.is_(True))
    return list(db.scalars(stmt.order_by(Project.name)).all())


def list_admins(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.role == UserRole.ADMIN)
            .order_by(User.last_name, User.first_name)
        ).all()
    )


def list_users(
    db: Session,
    *,
    role: UserRole | None = None,
    project_id: int | None = None,
) -> list[User]:
    stmt = select(User).options(selectinload(User.memberships))
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
    return list(db.scalars(stmt.order_by(User.last_name, User.first_name)).all())


def list_project_summaries(db: Session) -> list[ProjectSummary]:
    projects = list_projects(db)
    if not projects:
        return []
    ids = [p.id for p in projects]
    member_counts: dict[int, int] = {
        int(project_id): int(count)
        for project_id, count in db.execute(
            select(ProjectMember.project_id, func.count())
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.project_id.in_(ids),
                User.role != UserRole.ADMIN,
            )
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
    db: Session, project: Project, *, include_admins: bool = True
) -> list[User]:
    members = [m.user for m in project.members if m.user and not m.user.is_admin]
    members.sort(key=lambda u: (u.last_name.lower(), u.first_name.lower()))
    if not include_admins:
        return members
    return [*list_admins(db), *members]


def list_addable_users(db: Session, project: Project) -> list[User]:
    member_ids = {m.user_id for m in project.members}
    return [u for u in list_users(db) if not u.is_admin and u.id not in member_ids]


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
    clean_name = name.strip()
    if not clean_name:
        raise ValueError(t(lang, "messages.projects.name_required"))
    if _name_taken(db, clean_name, exclude_id=exclude_id):
        raise ValueError(t(lang, "messages.projects.name_exists"))
    clean_key = validate_project_key(key, lang=lang)
    if _key_taken(db, clean_key, exclude_id=exclude_id):
        raise ValueError(t(lang, "messages.projects.key_exists"))
    clean_description = (description or "").strip() or None
    return clean_name, clean_key, clean_description


def create_project(
    db: Session,
    name: str,
    key: str,
    description: str | None = None,
    *,
    lang: str | None = None,
) -> Project:
    clean_name, clean_key, clean_description = _normalize_project_fields(
        db, name, key, description, lang=lang or DEFAULT_LANG
    )
    project = Project(
        name=clean_name,
        key=clean_key,
        description=clean_description,
    )
    db.add(project)
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
    lang: str | None = None,
) -> Project:
    clean_name, clean_key, clean_description = _normalize_project_fields(
        db, name, key, description, exclude_id=project.id, lang=lang or DEFAULT_LANG
    )
    project.name = clean_name
    project.key = clean_key
    project.description = clean_description
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
    role = db.scalar(select(User.role).where(User.id == user_id))
    if role == UserRole.ADMIN:
        return True
    return _membership_row(db, project_id, user_id) is not None


def add_project_member(db: Session, project_id: int, user_id: int) -> None:
    user = db.get(User, user_id)
    if not user or user.is_admin:
        return
    if _membership_row(db, project_id, user_id) is not None:
        return
    db.add(ProjectMember(project_id=project_id, user_id=user_id))
    db.commit()


def remove_project_member(db: Session, project_id: int, user_id: int) -> None:
    user = db.get(User, user_id)
    if user and user.is_admin:
        return
    row = _membership_row(db, project_id, user_id)
    if row:
        db.delete(row)
        db.commit()


def clear_user_memberships(db: Session, user_id: int) -> None:
    for row in db.scalars(
        select(ProjectMember).where(ProjectMember.user_id == user_id)
    ).all():
        db.delete(row)
    db.flush()


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
    user = db.get(User, user_id)
    if user and user.is_admin:
        clear_user_memberships(db, user_id)
        return
    wanted = set(resolve_project_ids(db, project_ids, lang=lang))
    current = list(
        db.scalars(select(ProjectMember).where(ProjectMember.user_id == user_id)).all()
    )
    current_ids = {m.project_id for m in current}
    for row in current:
        if row.project_id not in wanted:
            db.delete(row)
    for pid in wanted - current_ids:
        db.add(ProjectMember(project_id=pid, user_id=user_id))
    db.flush()
