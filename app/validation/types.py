from __future__ import annotations

import re
import string
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.validation.spec import FieldSpec

_SPECIAL_RE = re.compile(rf"[{re.escape(string.punctuation)}]")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BLANK_EDGE_LINE_RE = re.compile(r"^(?:&nbsp;|\u00a0|\s)*$")


class FieldValidationError(Exception):
    def __init__(
        self,
        code: str,
        field: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.field = field
        self.params = params or {}
        super().__init__(code, field)


class ValidationValueError(ValueError):
    def __init__(self, message: str, *, field: str, code: str) -> None:
        super().__init__(message)
        self.field = field
        self.code = code


def trim_blank_edges(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and _BLANK_EDGE_LINE_RE.fullmatch(lines[0]):
        lines.pop(0)
    while lines and _BLANK_EDGE_LINE_RE.fullmatch(lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()


def normalize_raw(value: Any, spec: FieldSpec) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if spec.strip:
        value = value.strip()
    if spec.trim_blank_edges:
        value = trim_blank_edges(value)
    if spec.collapse_spaces:
        value = " ".join(value.split())
    if spec.case == "lower":
        value = value.lower()
    elif spec.case == "upper":
        value = value.upper()
    if spec.field_type == "phone" and value:
        value = re.sub(r"[\s\-()]", "", value)
    return value


def apply_type(field_id: str, value: str, spec: FieldSpec) -> str:
    if spec.field_type == "password":
        return _validate_password(field_id, value, spec)
    if spec.field_type == "email":
        return _validate_email(field_id, value, spec)
    if spec.field_type == "enum":
        return _validate_enum(field_id, value, spec)
    if spec.field_type == "timezone":
        return _validate_timezone(field_id, value, spec)
    return _validate_text(field_id, value, spec)


def _check_length(field_id: str, value: str, spec: FieldSpec) -> None:
    length = len(value)
    if spec.min_len is not None and length < spec.min_len:
        raise FieldValidationError(
            "too_short",
            field_id,
            params={"min": spec.min_len, "max": spec.max_len},
        )
    if spec.max_len is not None and length > spec.max_len:
        raise FieldValidationError(
            "too_long",
            field_id,
            params={"min": spec.min_len, "max": spec.max_len},
        )
    if spec.max_bytes is not None and len(value.encode("utf-8")) > spec.max_bytes:
        raise FieldValidationError(
            "too_long",
            field_id,
            params={"min": spec.min_len, "max": spec.max_bytes},
        )


def _validate_text(field_id: str, value: str, spec: FieldSpec) -> str:
    _check_length(field_id, value, spec)
    if spec.pattern and not re.fullmatch(spec.pattern, value, spec.pattern_flags):
        raise FieldValidationError(
            "pattern",
            field_id,
            params={"min": spec.min_len, "max": spec.max_len},
        )
    return value


def _validate_email(field_id: str, value: str, spec: FieldSpec) -> str:
    _check_length(field_id, value, spec)
    if not _EMAIL_RE.fullmatch(value):
        raise FieldValidationError("invalid", field_id)
    return value


def _validate_enum(field_id: str, value: str, spec: FieldSpec) -> str:
    if not spec.enum_values or value not in spec.enum_values:
        raise FieldValidationError("invalid", field_id)
    return value


def _validate_timezone(field_id: str, value: str, spec: FieldSpec) -> str:
    _check_length(field_id, value, spec)
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, KeyError, ValueError) as exc:
        raise FieldValidationError("invalid", field_id) from exc
    return value


def _validate_password(field_id: str, value: str, spec: FieldSpec) -> str:
    from app.config import get_settings

    settings = get_settings()
    min_len = spec.min_len if spec.min_len is not None else settings.password_min_len
    max_len = spec.max_len if spec.max_len is not None else settings.password_max_len
    if len(value) < min_len:
        raise FieldValidationError(
            "too_short",
            field_id,
            params={"min": min_len, "max": max_len, "reason": "min_length"},
        )
    if len(value.encode("utf-8")) > max_len:
        raise FieldValidationError(
            "too_long",
            field_id,
            params={"min": min_len, "max": max_len, "reason": "too_long"},
        )
    if not re.search(r"[a-z]", value):
        raise FieldValidationError("invalid", field_id, params={"reason": "need_lower"})
    if not re.search(r"[A-Z]", value):
        raise FieldValidationError("invalid", field_id, params={"reason": "need_upper"})
    if not re.search(r"\d", value):
        raise FieldValidationError("invalid", field_id, params={"reason": "need_digit"})
    if not _SPECIAL_RE.search(value):
        raise FieldValidationError(
            "invalid", field_id, params={"reason": "need_special"}
        )
    return value
