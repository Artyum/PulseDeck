from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.utils.i18n import DEFAULT_LANG, t

logger = logging.getLogger("pulsedeck.timefmt")

DEFAULT_DATETIME_FORMAT = "ISO_8601"
DEFAULT_TIMEZONE = "UTC"

DATETIME_FORMAT_IDS = (
    "ISO_8601",
    "EU_DOT",
    "UK_SLASH",
    "US_SLASH",
    "TEXT_LONG",
    "RELATIVE",
)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_datetime_format(value: str | None) -> str:
    raw = (value or "").strip()
    return raw if raw in DATETIME_FORMAT_IDS else DEFAULT_DATETIME_FORMAT


def normalize_timezone(value: str | None) -> str:
    raw = (value or "").strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(raw)
        return raw
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return DEFAULT_TIMEZONE


def _zone(tz_name: str | None) -> ZoneInfo:
    return ZoneInfo(normalize_timezone(tz_name))


def _hm24(local: datetime) -> str:
    return f"{local.hour:02d}:{local.minute:02d}"


def _hm12(local: datetime, *, lang: str) -> str:
    h12 = local.hour % 12 or 12
    suffix = t(lang, "ui.time.am" if local.hour < 12 else "ui.time.pm")
    return f"{h12}:{local.minute:02d} {suffix}"


def _fmt_absolute(local: datetime, style: str, *, lang: str) -> str:
    if style == "ISO_8601":
        return f"{local.year:04d}-{local.month:02d}-{local.day:02d} {_hm24(local)}"
    if style == "EU_DOT":
        return f"{local.day:02d}.{local.month:02d}.{local.year}, {_hm24(local)}"
    if style == "UK_SLASH":
        return (
            f"{local.day:02d}/{local.month:02d}/{local.year}, {_hm12(local, lang=lang)}"
        )
    if style == "US_SLASH":
        return (
            f"{local.month:02d}/{local.day:02d}/{local.year}, {_hm12(local, lang=lang)}"
        )
    if style == "TEXT_LONG":
        month = t(lang, f"ui.time.month_abbr.{local.month}")
        return f"{local.day} {month} {local.year}, {_hm24(local)}"
    return _fmt_absolute(local, "EU_DOT", lang=lang)


def _fmt_relative(
    local: datetime,
    *,
    zone: ZoneInfo,
    lang: str,
    now: datetime | None,
) -> str:
    ref = _aware(now or datetime.now(timezone.utc)).astimezone(zone).date()
    day = local.date()
    time_part = _hm24(local)
    if day == ref:
        return t(lang, "ui.time.today_at", time=time_part)
    if day == ref - timedelta(days=1):
        return t(lang, "ui.time.yesterday_at", time=time_part)
    return _fmt_absolute(local, "EU_DOT", lang=lang)


def format_datetime(
    dt: datetime | None,
    style: str | None = None,
    *,
    tz: str | None = None,
    lang: str | None = None,
    now: datetime | None = None,
) -> str:
    if dt is None:
        return ""
    fmt = normalize_datetime_format(style)
    lang_id = lang or DEFAULT_LANG
    zone = _zone(tz)
    local = _aware(dt).astimezone(zone)
    if fmt == "RELATIVE":
        return _fmt_relative(local, zone=zone, lang=lang_id, now=now)
    return _fmt_absolute(local, fmt, lang=lang_id)


def list_datetime_formats(
    lang: str,
    *,
    tz: str | None = None,
    now: datetime | None = None,
) -> tuple[SimpleNamespace, ...]:
    sample = _aware(now or datetime.now(timezone.utc))
    return tuple(
        SimpleNamespace(
            id=fmt_id,
            name=format_datetime(sample, fmt_id, tz=tz, lang=lang, now=sample),
        )
        for fmt_id in DATETIME_FORMAT_IDS
    )


def _offset_seconds(tz_name: str, at: datetime) -> int | None:
    offset = at.astimezone(ZoneInfo(tz_name)).utcoffset()
    return int(offset.total_seconds()) if offset is not None else None


def _offset_label(tz_name: str, at: datetime) -> str:
    total = _offset_seconds(tz_name, at)
    if total is None:
        return "UTC"
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"UTC{sign}{hours}" if not minutes else f"UTC{sign}{hours}:{minutes:02d}"


COMMON_TIMEZONES = (
    "UTC",
    "Europe/London",
    "Europe/Dublin",
    "Europe/Lisbon",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Rome",
    "Europe/Amsterdam",
    "Europe/Brussels",
    "Europe/Vienna",
    "Europe/Stockholm",
    "Europe/Copenhagen",
    "Europe/Oslo",
    "Europe/Warsaw",
    "Europe/Prague",
    "Europe/Zurich",
    "Africa/Casablanca",
    "Africa/Lagos",
    "Africa/Cairo",
    "Africa/Johannesburg",
    "Africa/Nairobi",
    "Europe/Athens",
    "Europe/Helsinki",
    "Europe/Bucharest",
    "Europe/Kyiv",
    "Europe/Istanbul",
    "Asia/Jerusalem",
    "Asia/Riyadh",
    "Europe/Moscow",
    "Asia/Dubai",
    "Asia/Tehran",
    "Asia/Karachi",
    "Asia/Kolkata",
    "Asia/Kathmandu",
    "Asia/Dhaka",
    "Asia/Bangkok",
    "Asia/Jakarta",
    "Asia/Hong_Kong",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Asia/Kuala_Lumpur",
    "Asia/Manila",
    "Asia/Seoul",
    "Asia/Tokyo",
    "Australia/Perth",
    "Australia/Adelaide",
    "Australia/Sydney",
    "Australia/Brisbane",
    "Pacific/Auckland",
    "Pacific/Fiji",
    "Pacific/Honolulu",
    "America/Anchorage",
    "America/Los_Angeles",
    "America/Vancouver",
    "America/Denver",
    "America/Phoenix",
    "America/Chicago",
    "America/Mexico_City",
    "America/New_York",
    "America/Toronto",
    "America/Bogota",
    "America/Lima",
    "America/Caracas",
    "America/Halifax",
    "America/St_Johns",
    "America/Sao_Paulo",
    "America/Argentina/Buenos_Aires",
    "America/Santiago",
)


def list_timezones(
    *, now: datetime | None = None, current: str | None = None
) -> tuple[SimpleNamespace, ...]:
    at = _aware(now or datetime.now(timezone.utc))
    names: set[str] = set(COMMON_TIMEZONES)
    if DEFAULT_TIMEZONE not in names:
        names.add(DEFAULT_TIMEZONE)
    if current:
        names.add(current)
    rows: list[tuple[SimpleNamespace, int]] = []
    for name in names:
        try:
            offset = _offset_seconds(name, at)
            label = _offset_label(name, at)
        except (ZoneInfoNotFoundError, KeyError, ValueError, OSError) as exc:
            logger.debug("Skipping timezone %s: %s", name, exc)
            continue
        rows.append((SimpleNamespace(id=name, name=f"{name} ({label})"), offset or 0))
    rows.sort(key=lambda row: (row[1], row[0].name))
    return tuple(row[0] for row in rows)
