from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.ticket import Tag, Ticket
from app.models.user import Project, ProjectMember, User

DEFAULT_ENV = Path(__file__).resolve().parents[1] / "deploy" / ".env.dev"
DEFAULT_PROJECT_NAME = "Performance"
DEFAULT_PROJECT_KEY = "PERF"
TITLE_PREFIX = "Perf load"
TAG_PREFIX = "perf-"
USER_EMAIL_PREFIX = "perf-seed-"
STAFF_EMAIL_PREFIX = "perf-seed-staff-"
USER_EMAIL_DOMAIN = "perf.pulsedeck.test"

logger = logging.getLogger("pulsedeck.perf_seed")


def perf_user_email(seq: int) -> str:
    return f"{USER_EMAIL_PREFIX}{seq:03d}@{USER_EMAIL_DOMAIN}"


def perf_staff_email(seq: int) -> str:
    return f"{STAFF_EMAIL_PREFIX}{seq:03d}@{USER_EMAIL_DOMAIN}"


def perf_tag_name(seq: int) -> str:
    return f"{TAG_PREFIX}{seq:03d}"


def is_perf_test_email(email: str) -> bool:
    lowered = email.strip().lower()
    suffix = f"@{USER_EMAIL_DOMAIN}"
    if not lowered.endswith(suffix):
        return False
    local = lowered[: -len(suffix)]
    if local.startswith(STAFF_EMAIL_PREFIX):
        return True
    return local.startswith(USER_EMAIL_PREFIX) and not local.startswith(
        STAFF_EMAIL_PREFIX
    )


def load_runtime_env(env_path: Path | str) -> None:
    from scripts.load_env import apply_env_file

    path = Path(env_path)
    if path.is_file():
        apply_env_file(path, override=True)
    elif str(path) != str(DEFAULT_ENV):
        raise SystemExit(f"Brak pliku: {path}")
    os.environ.setdefault("DATABASE_URL", "sqlite://")
    os.environ.setdefault("STORAGE_SECRET", "seed-performance-secret")
    from app.config import get_settings

    get_settings.cache_clear()


def log_db_target() -> None:
    from app.config import get_settings

    url = get_settings().database_url
    if url.startswith("sqlite"):
        logger.info("Baza: sqlite (%s)", url)
        return
    host = url.split("@", 1)[-1].split("/", 1)[0]
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    logger.info("Baza: %s / %s", host, db_name)


def get_project(db: Session, name: str) -> Project | None:
    return db.scalar(select(Project).where(Project.name == name))


def ensure_project(
    db: Session,
    *,
    name: str = DEFAULT_PROJECT_NAME,
    key: str = DEFAULT_PROJECT_KEY,
    lang: str = "pl",
) -> Project:
    project = get_project(db, name)
    if project is not None:
        return project
    from app.models.enums import UserRole
    from app.services.projects import create_project

    staff = db.scalar(
        select(User)
        .where(
            User.role.in_((UserRole.STAFF, UserRole.ADMIN)), User.is_active.is_(True)
        )
        .order_by(User.id)
        .limit(1)
    )
    if staff is None:
        raise RuntimeError("Brak użytkownika Staff/Admin do utworzenia projektu perf.")
    project = create_project(
        db,
        name,
        key,
        description="Dane testów wydajnościowych (auto-seed).",
        initial_staff_ids=[staff.id],
        lang=lang,
    )
    logger.info("Utworzono projekt %r (key=%s)", name, project.key)
    return project


def count_perf_tickets(db: Session, project_id: int, prefix: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.project_id == project_id,
                Ticket.title.like(f"{prefix}%"),
            )
        )
        or 0
    )


def perf_test_user_ids(db: Session, project_id: int) -> list[int]:
    member_ids = select(ProjectMember.user_id).where(
        ProjectMember.project_id == project_id
    )
    other_members = select(ProjectMember.user_id).where(
        ProjectMember.project_id != project_id
    )
    rows = db.scalars(
        select(User.id)
        .where(
            User.id.in_(member_ids),
            or_(
                User.email.like(f"{USER_EMAIL_PREFIX}%@{USER_EMAIL_DOMAIN}"),
                User.email.like(f"{STAFF_EMAIL_PREFIX}%@{USER_EMAIL_DOMAIN}"),
            ),
            User.id.not_in(other_members),
        )
        .order_by(User.id)
    ).all()
    return list(rows)


def count_perf_users(db: Session, project_id: int) -> int:
    return len(perf_test_user_ids(db, project_id))


def count_perf_tags(db: Session, project_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Tag)
            .where(
                Tag.project_id == project_id,
                Tag.name.like(f"{TAG_PREFIX}%"),
            )
        )
        or 0
    )


def delete_perf_tickets(db: Session, project_id: int, prefix: str) -> int:
    ids = list(
        db.scalars(
            select(Ticket.id).where(
                Ticket.project_id == project_id,
                Ticket.title.like(f"{prefix}%"),
            )
        ).all()
    )
    if not ids:
        return 0
    db.execute(delete(Ticket).where(Ticket.id.in_(ids)))
    return len(ids)


def delete_perf_tags(db: Session, project_id: int) -> int:
    ids = list(
        db.scalars(
            select(Tag.id).where(
                Tag.project_id == project_id,
                Tag.name.like(f"{TAG_PREFIX}%"),
            )
        ).all()
    )
    if not ids:
        return 0
    db.execute(delete(Tag).where(Tag.id.in_(ids)))
    return len(ids)


def delete_perf_users(db: Session, project_id: int) -> int:
    ids = perf_test_user_ids(db, project_id)
    if not ids:
        return 0
    db.execute(delete(User).where(User.id.in_(ids)))
    return len(ids)


def delete_perf_data(
    db: Session,
    project_id: int,
    prefix: str,
    *,
    delete_users: bool = True,
    delete_tags: bool = True,
) -> tuple[int, int, int]:
    tickets_removed = delete_perf_tickets(db, project_id, prefix)
    users_removed = 0
    tags_removed = 0
    if delete_users:
        users_removed = delete_perf_users(db, project_id)
    if delete_tags:
        tags_removed = delete_perf_tags(db, project_id)
    db.commit()
    return tickets_removed, users_removed, tags_removed


def vacuum_db(db: Session) -> None:
    from sqlalchemy import text
    from sqlalchemy.engine import Engine

    bind = db.get_bind()
    engine = bind if isinstance(bind, Engine) else getattr(bind, "engine", None)
    if not isinstance(engine, Engine) or engine.dialect.name != "postgresql":
        logger.info("VACUUM pominięty (tylko PostgreSQL)")
        return
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(
            text(
                "VACUUM ANALYZE tickets, comments, users, project_members, tags, ticket_tags"
            )
        )
    logger.info(
        "VACUUM ANALYZE: tickets, comments, users, project_members, tags, ticket_tags"
    )


def ensure_perf_users(
    db: Session,
    project_id: int,
    count: int,
    *,
    locale: str,
    seed: int | None,
    role: UserRole = UserRole.USER,
    email_fn=perf_user_email,
) -> list[User]:
    from faker import Faker

    fake = Faker(locale)
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    users: list[User] = []
    for seq in range(1, count + 1):
        email = email_fn(seq)
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                role=role,
                is_active=True,
                activated_at=datetime.now(timezone.utc),
                ui_lang="pl",
            )
            db.add(user)
            db.flush()
        membership = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
            )
        )
        if membership is None:
            db.add(ProjectMember(project_id=project_id, user_id=user.id))
        users.append(user)

    db.commit()
    for user in users:
        db.refresh(user)
    return users


def ensure_perf_staff(
    db: Session,
    project_id: int,
    count: int,
    *,
    locale: str,
    seed: int | None,
) -> list[User]:
    staff_seed = (seed + 1) if seed is not None else None
    return ensure_perf_users(
        db,
        project_id,
        count,
        locale=locale,
        seed=staff_seed,
        role=UserRole.STAFF,
        email_fn=perf_staff_email,
    )


def ensure_perf_tags(
    db: Session,
    project_id: int,
    count: int,
) -> list[Tag]:
    from app.validation import clean

    tags: list[Tag] = []
    for seq in range(1, count + 1):
        name = clean("tag.name", perf_tag_name(seq), lang="pl")
        tag = db.scalar(
            select(Tag).where(
                Tag.project_id == project_id,
                func.lower(Tag.name) == name.lower(),
            )
        )
        if tag is None:
            tag = Tag(project_id=project_id, name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)

    db.commit()
    for tag in tags:
        db.refresh(tag)
    return tags


def pick_ticket_status(rng: random.Random):
    from app.models.enums import TicketStatus

    return rng.choice(list(TicketStatus))


def pick_ticket_priority(rng: random.Random):
    from app.models.enums import TicketPriority

    return rng.choice(list(TicketPriority))


def pick_ticket_type(rng: random.Random):
    from app.models.enums import TicketType

    return rng.choice(list(TicketType))


def pick_ticket_tags(
    tags: list[Tag], rng: random.Random, max_count: int = 5
) -> list[Tag]:
    if not tags:
        return []
    count = rng.randint(0, max_count)
    if count == 0:
        return []
    return rng.sample(tags, min(count, len(tags)))


def ensure_project_membership(db: Session, project_id: int, user_id: int) -> None:
    exists = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if exists is None:
        db.add(ProjectMember(project_id=project_id, user_id=user_id))


def resolve_viewers(db: Session, project_id: int) -> list[User]:
    from app.config import get_settings

    settings = get_settings()
    viewers: list[User] = []
    seen: set[int] = set()

    def add(user: User | None) -> None:
        if user is None or user.id in seen:
            return
        if user.role not in (UserRole.STAFF, UserRole.ADMIN):
            return
        if is_perf_test_email(user.email):
            return
        seen.add(user.id)
        viewers.append(user)

    admin_email = (settings.admin_email or "").strip().lower()
    if admin_email:
        add(db.scalar(select(User).where(User.email == admin_email)))

    for user in db.scalars(
        select(User)
        .where(User.role.in_([UserRole.STAFF, UserRole.ADMIN]))
        .order_by(User.id)
    ).all():
        add(user)

    if not viewers:
        raise SystemExit(
            "Brak staff/admin — nie można przypisać wątków do widoku „moje”."
        )

    for user in viewers:
        ensure_project_membership(db, project_id, user.id)
    db.flush()
    return viewers


def pick_assignee(viewers: list[User], seq: int) -> User:
    return viewers[seq % len(viewers)]


def project_feed_url(project_key: str) -> str:
    from app.config import get_settings

    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/p/{project_key}?view=all&mine=1"


def pick_author(users: list[User]) -> User:
    return random.choice(users)


def plan_conversation_roles(count: int, rng: random.Random) -> list[bool]:
    if count <= 0:
        return []
    if rng.random() < 0.95:
        is_staff = rng.choice((True, False))
        roles: list[bool] = []
        for _ in range(count):
            roles.append(is_staff)
            is_staff = not is_staff
        return roles
    roles = []
    is_staff = True
    streak_left = 0
    while len(roles) < count:
        if streak_left <= 0:
            if roles:
                is_staff = not is_staff
            streak_left = rng.randint(1, 3)
        roles.append(is_staff)
        streak_left -= 1
    return roles
