from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import MagicTokenPurpose
from app.models.ticket import MagicToken, Ticket
from app.models.user import User
from app.services import tickets as ticket_service
from app.services.auth import (
    create_magic_token,
    hash_magic_token,
    login_blocked_reason,
    token_expires_at,
)

logger = logging.getLogger("pulsedeck.reply_token")


class ReplyTokenStatus(str, Enum):
    OK = "ok"
    INVALID = "invalid"
    USED = "used"
    EXPIRED = "expired"


def create_reply_token(db: Session, user: User, ticket: Ticket) -> str:
    _row, raw = create_magic_token(
        db,
        user,
        purpose=MagicTokenPurpose.TICKET_REPLY,
        ticket_id=ticket.id,
    )
    return raw


def lookup_reply_token(db: Session, raw: str) -> MagicToken | None:
    return db.scalar(
        select(MagicToken).where(
            MagicToken.token == hash_magic_token(raw),
            MagicToken.purpose == MagicTokenPurpose.TICKET_REPLY.value,
        )
    )


def classify_reply_token(row: MagicToken | None) -> ReplyTokenStatus:
    if row is None or row.ticket_id is None:
        return ReplyTokenStatus.INVALID
    if row.used_at is not None:
        return ReplyTokenStatus.USED
    if token_expires_at(row) <= datetime.now(timezone.utc):
        return ReplyTokenStatus.EXPIRED
    return ReplyTokenStatus.OK


def resolve_reply_token(db: Session, raw: str) -> MagicToken | None:
    row = lookup_reply_token(db, raw)
    return row if classify_reply_token(row) == ReplyTokenStatus.OK else None


def load_reply_context(db: Session, row: MagicToken) -> tuple[User, Ticket] | None:
    user = db.get(User, row.user_id)
    if not user or login_blocked_reason(user) is not None or not row.ticket_id:
        return None
    ticket = ticket_service.get_ticket(db, row.ticket_id)
    if not ticket or not ticket_service.is_project_member(
        db, ticket.project_id, user.id
    ):
        return None
    return user, ticket


def lock_reply_token(db: Session, token_id: int) -> MagicToken | None:
    return db.scalar(
        select(MagicToken).where(MagicToken.id == token_id).with_for_update()
    )


def consume_reply_token(row: MagicToken) -> None:
    row.used_at = datetime.now(timezone.utc)


def _sign_reply_file(body: str) -> str:
    return hmac.new(
        get_settings().storage_secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def make_reply_file_url(attachment_id: int, *, ticket_id: int) -> str:
    exp = int(time.time()) + int(get_settings().reply_file_sig_ttl_seconds)
    body = f"{attachment_id}.{ticket_id}.{exp}"
    qs = urlencode({"exp": exp, "sig": _sign_reply_file(body), "ticket_id": ticket_id})
    return f"/reply-file/{attachment_id}?{qs}"


def verify_reply_file_sig(
    attachment_id: int, *, ticket_id: int, exp: int, sig: str
) -> bool:
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i < int(time.time()):
        return False
    expected = _sign_reply_file(f"{attachment_id}.{ticket_id}.{exp_i}")
    try:
        return hmac.compare_digest(sig or "", expected)
    except (TypeError, ValueError):
        return False


def attachment_file_urls(ticket: Ticket, user: User) -> dict[int, str]:
    urls: dict[int, str] = {
        att.id: make_reply_file_url(att.id, ticket_id=ticket.id)
        for att in ticket.attachments or []
    }
    for comment in ticket.comments or []:
        if comment.is_internal and not user.is_staff:
            continue
        for att in comment.attachments or []:
            urls[att.id] = make_reply_file_url(att.id, ticket_id=ticket.id)
    return urls


def log_reply_token_event(
    *,
    result: str,
    user_id: int | None = None,
    token_id: int | None = None,
    token_hash: str | None = None,
    ticket_id: int | None = None,
    ip: str | None = None,
    ua: str | None = None,
) -> None:
    logger.info(
        "reply_token result=%s user_id=%s token_id=%s token_hash=%s "
        "ticket_id=%s ip=%s ua=%s",
        result,
        user_id,
        token_id,
        (token_hash or "")[:16] or None,
        ticket_id,
        ip,
        (ua or "")[:200] or None,
    )
