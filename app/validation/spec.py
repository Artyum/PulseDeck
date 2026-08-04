from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class FieldSpec:
    field_type: str
    required: bool = True
    min_len: int | None = None
    max_len: int | None = None
    max_bytes: int | None = None
    pattern: str | None = None
    pattern_flags: int = 0
    enum_values: frozenset[str] | None = None
    strip: bool = True
    case: str | None = None
    collapse_spaces: bool = False
    trim_blank_edges: bool = False
    html_input_type: str | None = None
    html_pattern: str | None = None

    def html_attrs(self) -> dict[str, str]:
        attrs: dict[str, str] = {}
        if self.required:
            attrs["required"] = "required"
        if self.max_len is not None:
            attrs["maxlength"] = str(self.max_len)
        if self.min_len is not None and self.field_type == "password":
            attrs["minlength"] = str(self.min_len)
        pattern = self.html_pattern or self.pattern
        if pattern:
            attrs["pattern"] = pattern
        if self.html_input_type:
            attrs["type"] = self.html_input_type
        return attrs


def enum_values(enum_cls: type[Enum]) -> frozenset[str]:
    return frozenset(member.value for member in enum_cls)


def text(
    *,
    required: bool = True,
    min_len: int | None = None,
    max_len: int,
    collapse_spaces: bool = False,
    case: str | None = None,
    trim_blank_edges: bool = False,
) -> FieldSpec:
    return FieldSpec(
        field_type="text",
        required=required,
        min_len=min_len,
        max_len=max_len,
        collapse_spaces=collapse_spaces,
        case=case,
        trim_blank_edges=trim_blank_edges,
    )


def email(*, required: bool = True) -> FieldSpec:
    return FieldSpec(
        field_type="email",
        required=required,
        max_len=320,
        case="lower",
        html_input_type="email",
    )


def phone(*, required: bool = False) -> FieldSpec:
    return FieldSpec(
        field_type="phone",
        required=required,
        max_len=20,
        pattern=r"^\+[1-9]\d{7,14}$",
        html_input_type="tel",
        html_pattern=r"\+[1-9]\d{7,14}",
    )


def password(*, required: bool = True) -> FieldSpec:
    from app.config import get_settings

    settings = get_settings()
    return FieldSpec(
        field_type="password",
        required=required,
        min_len=settings.password_min_len,
        max_len=settings.password_max_len,
        strip=False,
        html_input_type="password",
    )


def key(*, required: bool = True) -> FieldSpec:
    return FieldSpec(
        field_type="key",
        required=required,
        min_len=1,
        max_len=5,
        case="upper",
        pattern=r"^[A-Z0-9]{1,5}$",
        html_pattern=r"[A-Za-z0-9]{1,5}",
    )


def enum_field(
    values: frozenset[str] | type[Enum],
    *,
    required: bool = True,
) -> FieldSpec:
    if isinstance(values, type) and issubclass(values, Enum):
        allowed: frozenset[str] = enum_values(values)
    else:
        allowed = values
    return FieldSpec(
        field_type="enum",
        required=required,
        enum_values=allowed,
    )


def timezone(*, required: bool = True) -> FieldSpec:
    return FieldSpec(field_type="timezone", required=required, max_len=64)
