from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session as db_session
from app.models.portal_settings import PortalSetting

logger = logging.getLogger("pulsedeck.portal_settings")

_CACHE_TTL_S = 5.0
_SECRET_SALT = "portal-setting-secret"
_BOOL_TRUE = frozenset({"1", "true", "on", "yes"})

Kind = Literal["str", "int", "bool"]

SMTP_SECURITY_NONE = "none"
SMTP_SECURITY_STARTTLS = "starttls"
SMTP_SECURITY_SSL = "ssl"
SMTP_SECURITY_VALUES = frozenset(
    {SMTP_SECURITY_NONE, SMTP_SECURITY_STARTTLS, SMTP_SECURITY_SSL}
)

SECTION_KEYS: dict[str, tuple[str, ...]] = {
    "tickets": (
        "ticket_reopen_days",
        "auth_link_ttl_days",
        "email_confirm_ttl_minutes",
    ),
    "uploads": (
        "upload_max_image_bytes",
        "upload_max_file_bytes",
        "upload_max_files",
    ),
    "mail": (
        "smtp_server",
        "smtp_port",
        "smtp_security",
        "smtp_user",
        "smtp_pass",
        "email_from",
    ),
}


@dataclass(frozen=True, slots=True)
class SettingDef:
    kind: Kind
    secret: bool = False
    min_int: int | None = None
    max_int: int | None = None
    choices: frozenset[str] | None = None


REGISTRY: dict[str, SettingDef] = {
    "ticket_reopen_days": SettingDef("int", min_int=0, max_int=3650),
    "auth_link_ttl_days": SettingDef("int", min_int=1, max_int=365),
    "email_confirm_ttl_minutes": SettingDef("int", min_int=5, max_int=10_080),
    "upload_max_image_bytes": SettingDef("int", min_int=1, max_int=100 * 1024 * 1024),
    "upload_max_file_bytes": SettingDef("int", min_int=1, max_int=500 * 1024 * 1024),
    "upload_max_files": SettingDef("int", min_int=1, max_int=50),
    "smtp_server": SettingDef("str"),
    "smtp_port": SettingDef("int", min_int=1, max_int=65535),
    "smtp_security": SettingDef("str", choices=SMTP_SECURITY_VALUES),
    "smtp_user": SettingDef("str"),
    "smtp_pass": SettingDef("str", secret=True),
    "email_from": SettingDef("str"),
}


@dataclass(frozen=True, slots=True)
class PortalSettings:
    ticket_reopen_days: int
    auth_link_ttl_days: int
    email_confirm_ttl_minutes: int
    upload_max_image_bytes: int
    upload_max_file_bytes: int
    upload_max_files: int
    smtp_server: str
    smtp_port: int
    smtp_security: str
    smtp_user: str
    smtp_pass: str
    email_from: str

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_server.strip())

    @property
    def email_from_address(self) -> str:
        return (self.email_from or self.smtp_user).strip()


_cache: PortalSettings | None = None
_cache_at: float = 0.0


def invalidate_cache() -> None:
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _BOOL_TRUE


def _secret_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().storage_secret, salt=_SECRET_SALT)


def _encrypt_secret(plain: str) -> str:
    return _secret_serializer().dumps(plain) if plain else ""


def _decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        value = _secret_serializer().loads(token)
    except BadSignature:
        logger.warning("Portal setting secret failed to decrypt")
        return ""
    except Exception:
        logger.exception("Failed to decrypt portal setting secret")
        return ""
    return str(value) if value is not None else ""


def _env_seed_plain() -> dict[str, Any]:
    s = get_settings()
    return {
        "ticket_reopen_days": s.ticket_reopen_days,
        "auth_link_ttl_days": s.auth_link_ttl_days,
        "email_confirm_ttl_minutes": s.email_confirm_ttl_minutes,
        "upload_max_image_bytes": s.upload_max_image_bytes,
        "upload_max_file_bytes": s.upload_max_file_bytes,
        "upload_max_files": s.upload_max_files,
        "smtp_server": s.smtp_server,
        "smtp_port": s.smtp_port,
        "smtp_security": (SMTP_SECURITY_SSL if s.smtp_use_ssl else SMTP_SECURITY_NONE),
        "smtp_user": s.smtp_user,
        "smtp_pass": s.smtp_pass,
        "email_from": s.email_from,
    }


def _to_stored(defn: SettingDef, value: Any) -> str:
    if defn.secret:
        return _encrypt_secret(str(value or ""))
    if defn.kind == "bool":
        return "true" if _as_bool(value) else "false"
    if defn.kind == "int":
        return str(int(value))
    return str(value if value is not None else "")


def _from_stored(defn: SettingDef, raw: str) -> Any:
    if defn.secret:
        return _decrypt_secret(raw)
    if defn.kind == "bool":
        return _as_bool(raw)
    if defn.kind == "int":
        return int(raw)
    return raw


def _validate(defn: SettingDef, value: Any, *, lang: str) -> Any:
    from app.utils.i18n import t

    if defn.kind == "bool":
        return _as_bool(value)
    if defn.kind == "int":
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(t(lang, "messages.admin.settings_invalid_int")) from exc
        if defn.min_int is not None and number < defn.min_int:
            raise ValueError(t(lang, "messages.admin.settings_out_of_range"))
        if defn.max_int is not None and number > defn.max_int:
            raise ValueError(t(lang, "messages.admin.settings_out_of_range"))
        return number
    text = str(value if value is not None else "").strip()
    if defn.choices is not None and text not in defn.choices:
        raise ValueError(t(lang, "messages.admin.settings_invalid_choice"))
    return text


def _migrate_smtp_security(db: Session) -> None:
    if db.get(PortalSetting, "smtp_security") is not None:
        return
    legacy = db.get(PortalSetting, "smtp_use_ssl")
    if legacy is None:
        return
    value = SMTP_SECURITY_SSL if _as_bool(legacy.value) else SMTP_SECURITY_NONE
    db.add(PortalSetting(key="smtp_security", value=value))
    db.delete(legacy)
    db.commit()
    invalidate_cache()
    logger.info("Migrated smtp_use_ssl → smtp_security=%s", value)


def ensure_portal_settings_seed(db: Session) -> None:
    _migrate_smtp_security(db)
    rows = list(db.scalars(select(PortalSetting)).all())
    existing = {row.key for row in rows}
    seed = _env_seed_plain()
    added = 0
    removed = 0
    for key, defn in REGISTRY.items():
        if key in existing:
            continue
        db.add(PortalSetting(key=key, value=_to_stored(defn, seed[key])))
        added += 1
    for row in rows:
        if row.key in REGISTRY:
            continue
        db.delete(row)
        removed += 1
    if added or removed:
        db.commit()
        invalidate_cache()
        logger.info("Portal settings seed added=%s removed=%s", added, removed)


def _build(db_raw: dict[str, str]) -> PortalSettings:
    seed = _env_seed_plain()
    raw = dict(db_raw)
    if "smtp_security" not in raw and "smtp_use_ssl" in raw:
        raw["smtp_security"] = (
            SMTP_SECURITY_SSL if _as_bool(raw["smtp_use_ssl"]) else SMTP_SECURITY_NONE
        )
    values: dict[str, Any] = {}
    for key, defn in REGISTRY.items():
        if key in raw:
            try:
                values[key] = _from_stored(defn, raw[key])
                continue
            except Exception:
                logger.exception("Invalid portal setting %s — using env seed", key)
        values[key] = seed[key]
    return PortalSettings(**values)


def get_portal_settings(db: Session | None = None) -> PortalSettings:
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and now - _cache_at < _CACHE_TTL_S:
        return _cache

    close = False
    session = db
    if session is None:
        session = db_session.SessionLocal()
        close = True
    try:
        raw = {
            row.key: row.value for row in session.scalars(select(PortalSetting)).all()
        }
        _cache = _build(raw)
        _cache_at = now
        return _cache
    finally:
        if close:
            session.close()


def update_section(
    db: Session,
    section: str,
    values: dict[str, Any],
    *,
    lang: str = "en",
) -> PortalSettings:
    keys = SECTION_KEYS.get(section)
    if not keys:
        raise ValueError("unknown section")

    rows = {
        row.key: row
        for row in db.scalars(
            select(PortalSetting).where(PortalSetting.key.in_(keys))
        ).all()
    }
    try:
        for key in keys:
            if key not in values:
                continue
            defn = REGISTRY[key]
            if defn.secret:
                plain = str(values[key] or "")
                if not plain.strip():
                    continue
                stored = _encrypt_secret(plain)
            else:
                stored = _to_stored(defn, _validate(defn, values[key], lang=lang))
            row = rows.get(key)
            if row is None:
                db.add(PortalSetting(key=key, value=stored))
            else:
                row.value = stored
        db.commit()
    except Exception:
        db.rollback()
        raise
    invalidate_cache()
    return get_portal_settings(db)


def form_values_for_section(section: str, db: Session | None = None) -> dict[str, Any]:
    ps = get_portal_settings(db)
    out: dict[str, Any] = {}
    for key in SECTION_KEYS.get(section, ()):
        defn = REGISTRY[key]
        if defn.secret:
            out[key] = ""
            out[f"{key}_set"] = bool(getattr(ps, key))
        else:
            out[key] = getattr(ps, key)
    return out
