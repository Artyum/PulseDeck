from __future__ import annotations

import hashlib
import hmac

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User

NOTIFY_PREFS = frozenset({"notify_new_ticket", "notify_reply", "notify_ticket_update"})


def _sign(body: str) -> str:
    return hmac.new(
        get_settings().storage_secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def make_unsubscribe_token(user_id: int, pref: str) -> str:
    if pref not in NOTIFY_PREFS:
        raise ValueError(f"invalid notify pref: {pref}")
    body = f"{user_id}.{pref}"
    return f"{body}.{_sign(body)}"


def parse_unsubscribe_token(token: str) -> tuple[int, str] | None:
    parts = (token or "").strip().split(".")
    if len(parts) != 3:
        return None
    uid_s, pref, sig = parts
    if pref not in NOTIFY_PREFS:
        return None
    body = f"{uid_s}.{pref}"
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        user_id = int(uid_s)
    except ValueError:
        return None
    if user_id < 1:
        return None
    return user_id, pref


def make_unsubscribe_url(user_id: int, pref: str) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/email/unsubscribe?token={make_unsubscribe_token(user_id, pref)}"


def apply_unsubscribe(db: Session, user_id: int, pref: str) -> User | None:
    if pref not in NOTIFY_PREFS:
        return None
    user = db.get(User, user_id)
    if user is None:
        return None
    setattr(user, pref, False)
    db.commit()
    db.refresh(user)
    return user
