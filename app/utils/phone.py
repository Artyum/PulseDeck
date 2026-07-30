from __future__ import annotations

import re

from app.utils.i18n import DEFAULT_LANG, t

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(raw: str | None, *, lang: str | None = None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    compact = re.sub(r"[\s\-()]", "", cleaned)
    if not _E164_RE.match(compact):
        raise ValueError(t(lang or DEFAULT_LANG, "messages.phone.e164"))
    return compact
