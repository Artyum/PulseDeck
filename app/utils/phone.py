from __future__ import annotations

import re

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    compact = re.sub(r"[\s\-()]", "", cleaned)
    if not _E164_RE.match(compact):
        raise ValueError(
            "Telefon musi być w formacie międzynarodowym E.164 (np. +48123456789)."
        )
    return compact
