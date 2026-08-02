from __future__ import annotations

from app.utils.i18n import DEFAULT_LANG
from app.validation import clean


def normalize_phone(raw: str | None, *, lang: str | None = None) -> str | None:
    return clean(
        "user.phone", raw if raw is not None else "", lang=lang or DEFAULT_LANG
    )
