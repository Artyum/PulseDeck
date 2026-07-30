from __future__ import annotations

import re

from app.utils.i18n import DEFAULT_LANG, t

KEY_PATTERN = re.compile(r"^[A-Z0-9]{1,5}$")
KEY_MIN_LEN = 1
KEY_MAX_LEN = 5


def normalize_project_key(raw: str) -> str:
    return (raw or "").strip().upper()


def validate_project_key(raw: str, *, lang: str | None = None) -> str:
    key = normalize_project_key(raw)
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError(
            t(
                lang or DEFAULT_LANG,
                "messages.project_key.invalid",
                min=KEY_MIN_LEN,
                max=KEY_MAX_LEN,
            )
        )
    return key
