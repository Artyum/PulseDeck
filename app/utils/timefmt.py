from __future__ import annotations

from datetime import datetime, timezone


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def format_relative(delta_seconds: float) -> str:
    seconds = int(abs(delta_seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    days = hours // 24
    if days < 60:
        return f"{days} d"
    months = days // 30
    if months < 24:
        return f"{months} mies."
    years = days // 365
    return f"{years} lat"


def gap_between(earlier: datetime | None, later: datetime | None) -> str:
    if earlier is None or later is None:
        return ""
    return format_relative((_aware(later) - _aware(earlier)).total_seconds())
