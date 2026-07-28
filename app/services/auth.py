import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import MagicTokenPurpose, UserRole
from app.models.ticket import MagicToken
from app.models.user import User
from app.utils.password import (
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.utils.phone import normalize_phone

logger = logging.getLogger("pulsedeck.services.auth")


def normalize_email(email: str) -> str:
    return email.strip().lower()


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
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def login_blocked_reason(user: User) -> str | None:
    if not user.is_active:
        return "Konto jest zablokowane."
    if user.pending_email:
        return "Potwierdź nowy adres e-mail, zanim się zalogujesz."
    return None


def set_password(user: User, password: str) -> None:
    validate_password_strength(password)
    user.password_hash = hash_password(password)


def bump_auth_epoch(user: User) -> None:
    user.auth_epoch = int(user.auth_epoch or 0) + 1


def invalidate_magic_tokens(db: Session, user_id: int) -> None:
    rows = db.scalars(
        select(MagicToken).where(
            MagicToken.user_id == user_id,
            MagicToken.used.is_(False),
        )
    ).all()
    for row in rows:
        row.used = True
    db.flush()


def _token_expires_at(row: MagicToken) -> datetime:
    if row.expires_at.tzinfo:
        return row.expires_at
    return row.expires_at.replace(tzinfo=timezone.utc)


def peek_magic_token(
    db: Session,
    token: str,
    *,
    purpose: MagicTokenPurpose,
) -> MagicToken | None:
    row = db.scalar(select(MagicToken).where(MagicToken.token == token))
    if not row or row.used or row.purpose != purpose.value:
        return None
    if _token_expires_at(row) <= datetime.now(timezone.utc):
        return None
    return row


def create_magic_token(
    db: Session,
    user: User,
    *,
    purpose: MagicTokenPurpose = MagicTokenPurpose.LOGIN,
) -> MagicToken:
    settings = get_settings()
    row = MagicToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        purpose=purpose.value,
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=settings.magic_link_ttl_minutes),
        used=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_user_role(db: Session, user: User, role: UserRole) -> User:
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
            raise ValueError("Nie można usunąć roli ostatniego administratora.")
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def set_active(db: Session, target: User, *, actor: User, active: bool) -> User:
    if target.id == actor.id:
        raise ValueError("Nie możesz zablokować własnego konta.")
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
) -> User:
    fn = first_name.strip()
    ln = last_name.strip()
    if not fn or not ln:
        raise ValueError("Imię i nazwisko są wymagane.")
    user.first_name = fn
    user.last_name = ln
    user.phone = normalize_phone(phone)
    db.flush()
    return user


def request_email_change(db: Session, user: User, new_email: str) -> MagicToken:
    normalized = normalize_email(new_email)
    if not normalized:
        raise ValueError("E-mail jest wymagany.")
    if normalized == user.email:
        raise ValueError("Nowy e-mail jest taki sam jak obecny.")
    if email_taken(db, normalized, exclude_user_id=user.id):
        raise ValueError("Ten e-mail jest już zajęty.")
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
        row.used = True
        db.commit()
        return None
    user.email = user.pending_email
    user.pending_email = None
    bump_auth_epoch(user)
    row.used = True
    invalidate_magic_tokens(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def admin_set_email(db: Session, user: User, new_email: str) -> User:
    normalized = normalize_email(new_email)
    if not normalized:
        raise ValueError("E-mail jest wymagany.")
    if normalized != user.email and email_taken(
        db, normalized, exclude_user_id=user.id
    ):
        raise ValueError("Ten e-mail jest już zajęty.")
    if normalized != user.email:
        invalidate_magic_tokens(db, user.id)
        bump_auth_epoch(user)
    user.email = normalized
    user.pending_email = None
    db.flush()
    return user


def admin_set_password(db: Session, user: User, password: str) -> User:
    set_password(user, password)
    bump_auth_epoch(user)
    invalidate_magic_tokens(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def send_password_set_token(db: Session, user: User) -> MagicToken:
    invalidate_magic_tokens(db, user.id)
    return create_magic_token(db, user, purpose=MagicTokenPurpose.PASSWORD_SET)


def complete_password_set(db: Session, token: str, password: str) -> User | None:
    row = peek_magic_token(db, token, purpose=MagicTokenPurpose.PASSWORD_SET)
    if not row:
        return None
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        return None
    set_password(user, password)
    bump_auth_epoch(user)
    row.used = True
    invalidate_magic_tokens(db, user.id)
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
    )
    try:
        set_password(admin, password)
    except ValueError as exc:
        logger.error("Admin seed password invalid: %s", exc)
        return
    db.add(admin)
    db.commit()
    logger.info("Seeded admin user %s", email)
