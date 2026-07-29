from __future__ import annotations

import re

KEY_PATTERN = re.compile(r"^[A-Z0-9]{1,5}$")
KEY_MIN_LEN = 1
KEY_MAX_LEN = 5


def normalize_project_key(raw: str) -> str:
    return (raw or "").strip().upper()


def validate_project_key(raw: str) -> str:
    key = normalize_project_key(raw)
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError(
            f"Klucz musi mieć {KEY_MIN_LEN}–{KEY_MAX_LEN} znaków A–Z / 0–9 (bez myślników)."
        )
    return key
