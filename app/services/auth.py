import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import MagicTokenPurpose, UserRole
from app.models.ticket import MagicToken
from app.models.user import ProjectMember, User
from app.services import projects as project_service
from app.services.portal_settings import get_portal_settings
from app.utils.i18n import DEFAULT_LANG, normalize_lang, t
from app.utils.password import (
    hash_password,
    verify_password,
)
from app.utils.timefmt import normalize_datetime_format, normalize_timezone
from app.validation import clean, clean_many

logger = logging.getLogger("pulsedeck.auth")

DUMMY_PASSWORD_HASH = "$2b$12$vqkSTwVDgTzZlLVxe2RpiuMihWoqM7Hpn9bYUmpOaSjrjjM2wjmJC"


def hash_magic_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def email_taken(db: Session, email: str, *, exclude_user_id: int | None = None) -> bool:
    normalized = normalize_email(email)
    q = select(User.id).where(
        or_(User.email == normalized, User.pending_email == normalized)
    )
    if exclude_user_id is not None:
        q = q.where(User.id != exclude_user_id)
    return db.scalar(q) is not None


def authenticate_password(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user or not user.password_hash:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def record_login(db: Session, user: User) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        logger.exception("Failed to record login user_id=%s", user.id)
        db.rollback()


def login_blocked_reason(user: User, *, lang: str | None = None) -> str | None:
    lang = lang or DEFAULT_LANG
    if not user.is_active:
        return t(lang, "flash.auth.account_blocked")
    if user.activated_at is None:
        return t(lang, "flash.auth.account_not_activated")
    return None


def can_receive_password_link(user: User) -> bool:
    return bool(user.is_active)


def mark_activated(user: User) -> None:
    if user.activated_at is None:
        user.activated_at = datetime.now(timezone.utc)


def set_password(user: User, password: str, *, lang: str | None = None) -> None:
    lang = lang or DEFAULT_LANG
    password = clean("user.password", password, lang=lang)
    user.password_hash = hash_password(password, lang=lang)


def bump_auth_epoch(user: User) -> None:
    user.auth_epoch = int(user.auth_epoch or 0) + 1


def require_matching_passwords(
    password: str, confirm: str, *, lang: str | None = None
) -> None:
    if password != confirm:
        raise ValueError(t(lang or DEFAULT_LANG, "messages.auth.passwords_mismatch"))


def _require_names(first_name: str, last_name: str, *, lang: str) -> tuple[str, str]:
    data = clean_many(
        {
            "user.first_name": first_name,
            "user.last_name": last_name,
        },
        lang=lang,
    )
    return data["user.first_name"], data["user.last_name"]


def invalidate_magic_tokens(db: Session, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(MagicToken).where(
            MagicToken.user_id == user_id,
            MagicToken.used_at.is_(None),
        )
    ).all()
    for row in rows:
        row.used_at = now
    db.flush()


def token_expires_at(row: MagicToken) -> datetime:
    if row.expires_at.tzinfo:
        return row.expires_at
    return row.expires_at.replace(tzinfo=timezone.utc)


def peek_magic_token(
    db: Session,
    token: str,
    *,
    purpose: MagicTokenPurpose,
) -> MagicToken | None:
    hashed = hash_magic_token(token)
    row = db.scalar(select(MagicToken).where(MagicToken.token == hashed))
    if not row or row.used_at is not None or row.purpose != purpose.value:
        return None
    if token_expires_at(row) <= datetime.now(timezone.utc):
        return None
    return row


def create_magic_token(
    db: Session,
    user: User,
    *,
    purpose: MagicTokenPurpose,
    ticket_id: int | None = None,
) -> tuple[MagicToken, str]:
    settings = get_settings()
    portal = get_portal_settings(db)
    if purpose == MagicTokenPurpose.PASSWORD_SET:
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=portal.auth_link_ttl_days
        )
    elif purpose == MagicTokenPurpose.TICKET_REPLY:
        if ticket_id is None:
            raise ValueError("ticket_id required for ticket_reply tokens")
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.reply_token_ttl_hours
        )
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=portal.email_confirm_ttl_minutes
        )
    raw = secrets.token_urlsafe(32)
    row = MagicToken(
        user_id=user.id,
        ticket_id=ticket_id,
        token=hash_magic_token(raw),
        purpose=purpose.value,
        expires_at=expires_at,
        used_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, raw


def set_user_role(
    db: Session, user: User, role: UserRole, *, lang: str | None = None
) -> User:
    if user.role == UserRole.ADMIN and role != UserRole.ADMIN:
        admins = int(
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == UserRole.ADMIN)
            )
            or 0
        )
        if admins <= 1:
            raise ValueError(
                t(lang or DEFAULT_LANG, "messages.auth.cannot_demote_last_admin")
            )
    if project_service.user_has_staff_ops(user) and role == UserRole.USER:
        for mid in db.scalars(
            select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        ).all():
            if project_service.would_leave_project_without_staff(
                db, int(mid), excluding_user_id=user.id
            ):
                raise ValueError(
                    t(lang or DEFAULT_LANG, "messages.projects.last_staff")
                )
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def set_active(
    db: Session,
    target: User,
    *,
    actor: User,
    active: bool,
    lang: str | None = None,
) -> User:
    lang = lang or DEFAULT_LANG
    if target.id == actor.id:
        raise ValueError(t(lang, "messages.auth.cannot_block_self"))
    if not active and project_service.user_has_staff_ops(target):
        for mid in db.scalars(
            select(ProjectMember.project_id).where(ProjectMember.user_id == target.id)
        ).all():
            if project_service.would_leave_project_without_staff(
                db, int(mid), excluding_user_id=target.id
            ):
                raise ValueError(t(lang, "messages.projects.last_staff"))
    target.is_active = active
    if not active:
        bump_auth_epoch(target)
        invalidate_magic_tokens(db, target.id)
    db.commit()
    db.refresh(target)
    return target


def update_profile_fields(
    db: Session,
    user: User,
    *,
    first_name: str,
    last_name: str,
    phone: str | None,
    lang: str | None = None,
) -> User:
    lang = lang or DEFAULT_LANG
    data = clean_many(
        {
            "user.first_name": first_name,
            "user.last_name": last_name,
            "user.phone": phone or "",
        },
        lang=lang,
    )
    user.first_name = data["user.first_name"]
    user.last_name = data["user.last_name"]
    user.phone = data["user.phone"]
    db.flush()
    return user


def update_notification_prefs(
    db: Session,
    user: User,
    *,
    notify_new_ticket: bool,
    notify_reply: bool,
    notify_ticket_update: bool,
) -> User:
    user.notify_new_ticket = notify_new_ticket
    user.notify_reply = notify_reply
    user.notify_ticket_update = notify_ticket_update
    db.commit()
    db.refresh(user)
    return user


def update_ui_lang(db: Session, user: User, lang: str) -> User:
    user.ui_lang = clean("user.ui_lang", lang, lang=normalize_lang(None))
    db.commit()
    db.refresh(user)
    return user


def update_datetime_prefs(
    db: Session,
    user: User,
    *,
    datetime_format: str,
    timezone: str,
    lang: str | None = None,
) -> User:
    lang = lang or DEFAULT_LANG
    data = clean_many(
        {
            "user.datetime_format": datetime_format,
            "user.timezone": timezone,
        },
        lang=lang,
    )
    user.datetime_format = data["user.datetime_format"]
    user.timezone = data["user.timezone"]
    user.datetime_prefs_locked = True
    db.commit()
    db.refresh(user)
    return user


def apply_auto_datetime_prefs(
    db: Session,
    user: User,
    *,
    timezone: str,
    datetime_format: str,
    ui_lang: str | None = None,
) -> bool:
    values: dict = {
        "datetime_format": normalize_datetime_format(datetime_format),
        "timezone": normalize_timezone(timezone),
        "datetime_prefs_locked": True,
    }
    if ui_lang is not None:
        values["ui_lang"] = normalize_lang(ui_lang)
    result = db.execute(
        update(User)
        .where(User.id == user.id, User.datetime_prefs_locked.is_(False))
        .values(**values)
    )
    db.commit()
    db.refresh(user)
    rowcount = result.rowcount if isinstance(result, CursorResult) else 0
    return bool(rowcount)


def request_email_change(
    db: Session, user: User, new_email: str, *, lang: str | None = None
) -> tuple[MagicToken, str]:
    lang = lang or DEFAULT_LANG
    normalized = clean("user.email", new_email, lang=lang)
    if normalized == user.email:
        raise ValueError(t(lang, "messages.auth.email_unchanged"))
    if email_taken(db, normalized, exclude_user_id=user.id):
        raise ValueError(t(lang, "messages.auth.email_taken"))
    invalidate_magic_tokens(db, user.id)
    user.pending_email = normalized
    db.flush()
    return create_magic_token(db, user, purpose=MagicTokenPurpose.EMAIL_CONFIRM)


def confirm_email_change(db: Session, token: str) -> User | None:
    row = peek_magic_token(db, token, purpose=MagicTokenPurpose.EMAIL_CONFIRM)
    if not row:
        return None
    user = db.get(User, row.user_id)
    if not user or not user.pending_email:
        return None
    if email_taken(db, user.pending_email, exclude_user_id=user.id):
        row.used_at = datetime.now(timezone.utc)
        db.commit()
        return None
    user.email = user.pending_email
    user.pending_email = None
    bump_auth_epoch(user)
    row.used_at = datetime.now(timezone.utc)
    invalidate_magic_tokens(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def admin_set_email(
    db: Session, user: User, new_email: str, *, lang: str | None = None
) -> User:
    lang = lang or DEFAULT_LANG
    normalized = clean("user.email", new_email, lang=lang)
    if normalized != user.email and email_taken(
        db, normalized, exclude_user_id=user.id
    ):
        raise ValueError(t(lang, "messages.auth.email_taken"))
    if normalized != user.email:
        invalidate_magic_tokens(db, user.id)
        bump_auth_epoch(user)
    user.email = normalized
    user.pending_email = None
    db.flush()
    return user


def admin_set_password(
    db: Session, user: User, password: str, *, lang: str | None = None
) -> User:
    set_password(user, password, lang=lang)
    mark_activated(user)
    bump_auth_epoch(user)
    invalidate_magic_tokens(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def resolve_password_set_token(
    db: Session, token: str
) -> tuple[MagicToken, User] | None:
    row = peek_magic_token(db, token, purpose=MagicTokenPurpose.PASSWORD_SET)
    if not row:
        return None
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        return None
    return row, user


def create_password_link(
    db: Session, user: User, *, lang: str | None = None
) -> tuple[MagicToken, str]:
    if not can_receive_password_link(user):
        raise ValueError(t(lang or DEFAULT_LANG, "flash.auth.account_blocked"))
    invalidate_magic_tokens(db, user.id)
    return create_magic_token(db, user, purpose=MagicTokenPurpose.PASSWORD_SET)


def send_password_link(
    db: Session, user: User, *, lang: str | None = None
) -> MagicToken:
    from app.services.email import notify_password_set

    token_row, raw = create_password_link(db, user, lang=lang)
    notify_password_set(db, user, raw)
    return token_row


def complete_password_set(
    db: Session,
    token: str,
    password: str,
    *,
    phone: str | None = None,
    lang: str | None = None,
) -> User | None:
    lang = lang or DEFAULT_LANG
    resolved = resolve_password_set_token(db, token)
    if not resolved:
        return None
    row, user = resolved
    set_password(user, password, lang=lang)
    if user.activated_at is None and phone is not None:
        user.phone = clean("user.phone", phone, lang=lang)
    mark_activated(user)
    bump_auth_epoch(user)
    row.used_at = datetime.now(timezone.utc)
    invalidate_magic_tokens(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def create_user(
    db: Session,
    *,
    first_name: str,
    last_name: str,
    email: str,
    role: UserRole,
    project_ids: list[int],
    phone: str | None = None,
    lang: str | None = None,
    ui_lang: str | None = None,
    activate: bool = False,
) -> User:
    lang = normalize_lang(lang)
    user_lang = normalize_lang(ui_lang or lang)
    fn, ln = _require_names(first_name, last_name, lang=lang)
    normalized = clean("user.email", email, lang=lang)
    phone_val = clean("user.phone", phone or "", lang=lang)
    if email_taken(db, normalized):
        raise ValueError(t(lang, "messages.auth.user_exists_resend"))
    role_value = clean("user.role", role.value, lang=lang)
    role = UserRole(role_value)
    if role != UserRole.ADMIN:
        resolved_ids = project_service.resolve_project_ids(db, project_ids, lang=lang)
    else:
        resolved_ids = []
    user = User(
        email=normalized,
        first_name=fn,
        last_name=ln,
        phone=phone_val,
        role=role,
        is_active=True,
        activated_at=None,
        password_hash=None,
        ui_lang=user_lang,
    )
    db.add(user)
    db.flush()
    for pid in resolved_ids:
        db.add(ProjectMember(project_id=pid, user_id=user.id))
    if activate:
        mark_activated(user)
    db.commit()
    db.refresh(user)
    return user


def ensure_admin_seed(db: Session) -> None:
    settings = get_settings()
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password or ""
    if not email or not password:
        logger.info("ADMIN_EMAIL/ADMIN_PASSWORD not set — skipping admin seed")
        return
    if get_user_by_email(db, email):
        return
    admin = User(
        email=email,
        first_name=settings.admin_first_name or "Admin",
        last_name=settings.admin_last_name or "PulseDeck",
        role=UserRole.ADMIN,
        activated_at=datetime.now(timezone.utc),
    )
    try:
        set_password(admin, password)
    except ValueError as exc:
        logger.error("Admin seed password invalid: %s", exc)
        return
    db.add(admin)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Admin seed skipped — %s already exists", email)
        return
    logger.info("Seeded admin user %s", email)
