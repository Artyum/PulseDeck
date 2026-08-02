from __future__ import annotations

from app.utils.i18n import DEFAULT_LANG
from app.validation import clean
from app.validation.fields import FIELDS
from app.validation.types import normalize_raw


def normalize_project_key(raw: str) -> str:
    return normalize_raw(raw or "", FIELDS["project.key"]) or ""


def validate_project_key(raw: str, *, lang: str | None = None) -> str:
    return clean("project.key", raw, lang=lang or DEFAULT_LANG)
