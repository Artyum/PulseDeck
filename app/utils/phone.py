from __future__ import annotations

import re

from app.utils.i18n import DEFAULT_LANG
from app.validation import clean

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_PHONE_NOISE_RE = re.compile(r"[\s\-()]")


def normalize_phone(raw: str | None, *, lang: str | None = None) -> str | None:
    return clean(
        "user.phone", raw if raw is not None else "", lang=lang or DEFAULT_LANG
    )


def format_phone(raw: str | None) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    compact = _PHONE_NOISE_RE.sub("", text)
    if not _E164_RE.fullmatch(compact):
        return text
    digits = compact[1:]
    if digits.startswith("1") and len(digits) == 11:
        n = digits[1:]
        return f"+1 {n[:3]} {n[3:6]} {n[6:]}"
    for cc_len in (1, 2, 3):
        national = digits[cc_len:]
        if len(national) >= 6 and len(national) % 3 == 0:
            groups = [national[i : i + 3] for i in range(0, len(national), 3)]
            return f"+{digits[:cc_len]} " + " ".join(groups)
    return compact
