from __future__ import annotations

import hashlib
import hmac

from app.config import get_settings


def _sign(body: str) -> str:
    return hmac.new(
        get_settings().storage_secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def make_unwatch_token(user_id: int, ticket_id: int) -> str:
    body = f"{user_id}.{ticket_id}"
    return f"{body}.{_sign(body)}"


def parse_unwatch_token(token: str) -> tuple[int, int] | None:
    parts = (token or "").strip().split(".")
    if len(parts) != 3:
        return None
    uid_s, ticket_s, sig = parts
    body = f"{uid_s}.{ticket_s}"
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        user_id = int(uid_s)
        ticket_id = int(ticket_s)
    except ValueError:
        return None
    if user_id < 1 or ticket_id < 1:
        return None
    return user_id, ticket_id


def make_unwatch_url(user_id: int, ticket_id: int) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/email/unwatch?token={make_unwatch_token(user_id, ticket_id)}"
