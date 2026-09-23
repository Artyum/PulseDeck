"""E-mail MFA: kody, zaufane urządzenia (per user), cookie na wspólną przeglądarkę."""

from __future__ import annotations

import base64
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings
from app.models.enums import EmailOutboxPriority
from app.models.mfa import MfaChallenge, MfaTrustedDevice
from app.models.user import User
from app.services.email import enqueue_email, render_email_html
from app.utils.i18n import t
from app.utils.mfa_ttl import cookie_secure

logger = logging.getLogger("pulsedeck.mfa")

DEVICE_COOKIE = "mfa_device"
CODE_TTL_SECONDS = 10 * 60
CODE_DIGITS = 6
MAX_ATTEMPTS = 5
SESSION_MFA_USER_ID_KEY = "mfa_pending_user_id"
SESSION_MFA_AREA_KEY = "mfa_pending_area"


class MfaDeliveryError(Exception):
    """Kod MFA nie wszedł do kolejki e-mail."""


def _hmac_hex(value: str) -> str:
    secret = get_settings().storage_secret.encode("utf-8")
    return hmac.new(secret, value.encode("utf-8"), sha256).hexdigest()


def _sign_payload(payload: str) -> str:
    secret = get_settings().storage_secret.encode("utf-8")
    digest = hmac.new(secret, payload.encode("ascii"), sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def create_challenge(db: Session, user_id: int) -> str:
    db.execute(delete(MfaChallenge).where(MfaChallenge.user_id == user_id))
    code = generate_code()
    db.add(
        MfaChallenge(
            user_id=user_id,
            code_hash=_hmac_hex(f"mfa-code:{user_id}:{code}"),
            expires_at=datetime.now(UTC) + timedelta(seconds=CODE_TTL_SECONDS),
            attempts=0,
        )
    )
    db.flush()
    return code


def send_challenge_email(db: Session, user: User, *, locale: str) -> None:
    if not (user.email or "").strip():
        logger.error("MFA not queued: empty email user_id=%s", user.id)
        raise MfaDeliveryError("missing email")
    code = create_challenge(db, user.id)
    minutes = CODE_TTL_SECONDS // 60
    html = render_email_html(
        "mfa_code.html",
        {"code": code, "minutes": minutes, "user": user},
        lang=locale,
    )
    try:
        enqueue_email(
            db,
            to_email=user.email,
            subject=t(locale, "email.mfa.subject"),
            html_body=html,
            priority=EmailOutboxPriority.AUTH,
        )
    except Exception as exc:
        logger.exception("MFA not queued user_id=%s", user.id)
        raise MfaDeliveryError("queue") from exc
    logger.info("Queued MFA code: user_id=%s", user.id)


def verify_challenge(db: Session, user_id: int, code: str) -> bool:
    digits = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(digits) != CODE_DIGITS:
        return False
    row = db.scalar(
        select(MfaChallenge)
        .where(MfaChallenge.user_id == user_id)
        .order_by(MfaChallenge.id.desc())
    )
    if row is None:
        return False
    now = datetime.now(UTC)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < now or row.attempts >= MAX_ATTEMPTS:
        db.delete(row)
        db.flush()
        return False
    row.attempts += 1
    expected = _hmac_hex(f"mfa-code:{user_id}:{digits}")
    ok = hmac.compare_digest(row.code_hash, expected)
    if ok:
        db.delete(row)
    db.flush()
    return ok


def set_pending_mfa(request: Request, user_id: int, *, area: str | None = None) -> None:
    request.session[SESSION_MFA_USER_ID_KEY] = user_id
    if area:
        request.session[SESSION_MFA_AREA_KEY] = area


def get_pending_mfa_user_id(request: Request) -> int | None:
    raw = request.session.get(SESSION_MFA_USER_ID_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def get_pending_mfa_area(request: Request) -> str | None:
    raw = request.session.get(SESSION_MFA_AREA_KEY)
    return str(raw) if raw else None


def clear_pending_mfa(request: Request) -> None:
    request.session.pop(SESSION_MFA_USER_ID_KEY, None)
    request.session.pop(SESSION_MFA_AREA_KEY, None)


def _decode_device_map(raw: str | None) -> dict[str, str]:
    if not raw or "." not in raw:
        return {}
    payload, signature = raw.rsplit(".", 1)
    if not hmac.compare_digest(_sign_payload(payload), signature):
        return {}
    pad = "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
    except (ValueError, json.JSONDecodeError):
        return {}
    devices = data.get("d") if isinstance(data, dict) else None
    if not isinstance(devices, dict):
        return {}
    out: dict[str, str] = {}
    for key, token in devices.items():
        if isinstance(key, str) and isinstance(token, str) and key.isdigit() and token:
            out[key] = token
    return out


def _encode_device_map(devices: dict[str, str]) -> str:
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"v": 1, "d": devices}, separators=(",", ":")).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    return f"{payload}.{_sign_payload(payload)}"


def is_trusted_device(db: Session, request: Request, user_id: int) -> bool:
    token = _decode_device_map(request.cookies.get(DEVICE_COOKIE)).get(str(user_id))
    if not token:
        return False
    token_hash = _hmac_hex(f"mfa-device:{user_id}:{token}")
    row = db.scalar(
        select(MfaTrustedDevice).where(
            MfaTrustedDevice.user_id == user_id,
            MfaTrustedDevice.token_hash == token_hash,
        )
    )
    if row is None:
        return False
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        db.delete(row)
        db.flush()
        return False
    return True


def remember_device(
    db: Session, request: Request, response: Response, user_id: int
) -> None:
    settings = get_settings()
    days = settings.mfa_ttl_days
    token = secrets.token_urlsafe(32)
    db.add(
        MfaTrustedDevice(
            user_id=user_id,
            token_hash=_hmac_hex(f"mfa-device:{user_id}:{token}"),
            expires_at=datetime.now(UTC) + timedelta(days=days),
        )
    )
    db.flush()
    devices = _decode_device_map(request.cookies.get(DEVICE_COOKIE))
    devices[str(user_id)] = token
    response.set_cookie(
        key=DEVICE_COOKIE,
        value=_encode_device_map(devices),
        max_age=days * 24 * 3600,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_device_cookie_secure(),
    )


def _device_cookie_secure() -> bool:
    settings = get_settings()
    https = urlparse(settings.app_base_url).scheme == "https"
    return cookie_secure(settings.environment, https)


def revoke_trusted_devices(db: Session, user_id: int) -> None:
    db.execute(delete(MfaTrustedDevice).where(MfaTrustedDevice.user_id == user_id))
    db.flush()
