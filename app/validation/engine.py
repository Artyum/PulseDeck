from __future__ import annotations

from typing import Any

from markupsafe import Markup

from app.utils.i18n import DEFAULT_LANG, t
from app.validation.fields import FIELDS
from app.validation.spec import FieldSpec
from app.validation.types import (
    FieldValidationError,
    ValidationValueError,
    apply_type,
    normalize_raw,
)

__all__ = [
    "FieldValidationError",
    "ValidationValueError",
    "clean",
    "clean_many",
    "field_attrs",
    "field_spec",
    "format_error",
]


def field_spec(field_id: str) -> FieldSpec:
    try:
        spec = FIELDS[field_id]
    except KeyError as exc:
        raise KeyError(f"Unknown field: {field_id}") from exc
    if field_id == "user.password":
        from app.validation.spec import password as password_field

        return password_field(required=spec.required)
    return spec


def validate(field_id: str, value: Any) -> Any:
    spec = field_spec(field_id)
    normalized = normalize_raw(value, spec)
    if normalized is None or normalized == "":
        if spec.required:
            raise FieldValidationError("required", field_id)
        return None
    return apply_type(field_id, normalized, spec)


def format_error(lang: str, err: FieldValidationError) -> str:
    reason = err.params.get("reason")
    if err.field == "user.password" and reason:
        key = f"messages.password.{reason}"
        return t(lang, key, **{k: v for k, v in err.params.items() if k != "reason"})
    if err.field == "user.phone" and err.code == "pattern":
        return t(lang, "messages.phone.e164")
    if err.field == "project.key" and err.code == "pattern":
        return t(
            lang,
            "messages.project_key.invalid",
            min=err.params.get("min", 1),
            max=err.params.get("max", 5),
        )
    label = t(lang, f"messages.fields.labels.{err.field}")
    params = {
        "field": label,
        "min": err.params.get("min", ""),
        "max": err.params.get("max", ""),
    }
    return t(lang, f"messages.fields.{err.code}", **params)


def clean(field_id: str, value: Any, *, lang: str | None = None) -> Any:
    lang = lang or DEFAULT_LANG
    try:
        return validate(field_id, value)
    except FieldValidationError as exc:
        raise ValidationValueError(
            format_error(lang, exc), field=exc.field, code=exc.code
        ) from exc


def clean_many(values: dict[str, Any], *, lang: str | None = None) -> dict[str, Any]:
    return {
        field_id: clean(field_id, value, lang=lang)
        for field_id, value in values.items()
    }


def field_attrs(field_id: str, *, required: bool | None = None) -> Markup:
    spec = field_spec(field_id)
    attrs = spec.html_attrs()
    if required is False:
        attrs.pop("required", None)
    elif required is True:
        attrs["required"] = "required"
    parts: list[str] = []
    for name, value in attrs.items():
        if name == value:
            parts.append(name)
        else:
            escaped = (
                str(value)
                .replace("&", "&amp;")
                .replace('"', "&quot;")
                .replace("<", "&lt;")
            )
            parts.append(f'{name}="{escaped}"')
    return Markup(" ".join(parts))
