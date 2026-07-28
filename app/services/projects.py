from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.enums import UserRole
from app.models.ticket import InviteLink, InviteLinkProject
from app.models.user import Project, ProjectMember, User
from app.services.auth import get_user_by_email, set_password
from app.utils.project_key import validate_project_key


def list_projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.name)).all())


def list_user_projects(db: Session, user: User) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id)
            .order_by(Project.name)
        ).all()
    )


def get_project_by_key(db: Session, key: str) -> Project | None:
    normalized = (key or "").strip().upper()
    return db.scalar(
        select(Project)
        .where(Project.key == normalized)
        .options(selectinload(Project.members).selectinload(ProjectMember.user))
    )


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


def create_project(
    db: Session, name: str, key: str, description: str | None = None
) -> Project:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Nazwa projektu jest wymagana.")
    if _name_taken(db, clean_name):
        raise ValueError("Projekt o tej nazwie już istnieje.")
    clean_key = validate_project_key(key)
    if _key_taken(db, clean_key):
        raise ValueError("Projekt o tym key już istnieje.")
    project = Project(
        name=clean_name,
        key=clean_key,
        description=(description or "").strip() or None,
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
) -> Project:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Nazwa projektu jest wymagana.")
    if _name_taken(db, clean_name, exclude_id=project.id):
        raise ValueError("Projekt o tej nazwie już istnieje.")
    clean_key = validate_project_key(key)
    if _key_taken(db, clean_key, exclude_id=project.id):
        raise ValueError("Projekt o tym key już istnieje.")
    project.name = clean_name
    project.key = clean_key
    project.description = (description or "").strip() or None
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.commit()


def is_project_member(db: Session, project_id: int, user_id: int) -> bool:
    return (
        db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        is not None
    )


def add_project_member(db: Session, project_id: int, user_id: int) -> None:
    if is_project_member(db, project_id, user_id):
        return
    db.add(ProjectMember(project_id=project_id, user_id=user_id))
    db.commit()


def remove_project_member(db: Session, project_id: int, user_id: int) -> None:
    row = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if row:
        db.delete(row)
        db.commit()


def list_users(db: Session) -> list[User]:
    return list(
        db.scalars(select(User).order_by(User.last_name, User.first_name)).all()
    )


def create_invite(
    db: Session,
    *,
    created_by: User,
    project_ids: list[int],
    expires_days: int | None = None,
    max_uses: int | None = None,
) -> InviteLink:
    settings = get_settings()
    days = (
        expires_days
        if expires_days is not None
        else settings.invite_default_expiry_days
    )
    uses = max_uses if max_uses is not None else settings.invite_default_max_uses
    invite = InviteLink(
        token=secrets.token_urlsafe(24),
        created_by_id=created_by.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=days),
        max_uses=max(1, uses),
        used_count=0,
        revoked=False,
    )
    db.add(invite)
    db.flush()
    for pid in project_ids:
        db.add(InviteLinkProject(invite_id=invite.id, project_id=pid))
    db.commit()
    db.refresh(invite)
    return invite


def get_invite_by_token(db: Session, token: str) -> InviteLink | None:
    return db.scalar(
        select(InviteLink)
        .where(InviteLink.token == token)
        .options(
            selectinload(InviteLink.projects).selectinload(InviteLinkProject.project)
        )
    )


def revoke_invite(db: Session, invite: InviteLink) -> None:
    invite.revoked = True
    db.commit()


def list_invites(db: Session) -> list[InviteLink]:
    return list(
        db.scalars(
            select(InviteLink)
            .options(
                selectinload(InviteLink.projects).selectinload(
                    InviteLinkProject.project
                )
            )
            .order_by(InviteLink.created_at.desc())
        ).all()
    )


def register_via_invite(
    db: Session,
    invite: InviteLink,
    *,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
) -> User:
    if not invite.is_valid:
        raise ValueError("Link zaproszenia jest nieważny lub wygasł.")
    if get_user_by_email(db, email):
        raise ValueError("Konto z tym adresem e-mail już istnieje. Zaloguj się.")
    user = User(
        email=email.strip().lower(),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        role=UserRole.USER,
    )
    set_password(user, password)
    db.add(user)
    db.flush()
    for link_project in invite.projects:
        db.add(ProjectMember(project_id=link_project.project_id, user_id=user.id))
    invite.used_count += 1
    db.commit()
    db.refresh(user)
    return user
