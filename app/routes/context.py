from __future__ import annotations

import logging
from enum import Enum
from types import SimpleNamespace

from fastapi import Request
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from app.config import get_settings, project_root
from app.models.enums import (
    TicketPriority,
    TicketStatus,
    TicketType,
    UserRole,
)
from app.services.portal_settings import get_portal_settings
from app.utils.avatar import avatar_tone, user_initials
from app.utils.csrf import ensure_csrf_token
from app.utils.dev_page_info import build_dev_page_info
from app.utils.i18n import (
    DEFAULT_LANG,
    LANG_STORAGE_KEY,
    list_languages,
    resolve_lang,
    t,
    translations_prefix,
)
from app.utils.markdown import render_markdown_safe
from app.utils.phone import format_phone
from app.utils.static_assets import static_url
from app.utils.themes import (
    DEFAULT_DENSITY,
    DEFAULT_FONT_SIZE,
    DEFAULT_THEME,
    DEFAULT_THEME_GRADIENT,
    DEFAULT_THREAD_ORDER,
    DENSITY_CHOICES,
    DENSITY_STORAGE_KEY,
    FONT_SIZE_CHOICES,
    FONT_SIZE_STORAGE_KEY,
    THEME_CHOICES,
    THEME_GRADIENT_STORAGE_KEY,
    THEME_PAIRS,
    THEME_STORAGE_KEY,
    THREAD_ORDER_IDS,
    THREAD_ORDER_STORAGE_KEY,
    theme_scheme,
)
from app.utils.timefmt import (
    DEFAULT_DATETIME_FORMAT,
    DEFAULT_TIMEZONE,
    format_datetime,
    list_datetime_formats,
    list_timezones,
    normalize_datetime_format,
    normalize_timezone,
)
from app.utils.urls import (
    admin_project_path,
    attachment_path,
    build_feed_path,
    project_path,
    ticket_label,
    ticket_path,
)
from app.validation import field_attrs

logger = logging.getLogger("pulsedeck.app")

_templates = Jinja2Templates(directory=str(project_root() / "frontend" / "templates"))


@pass_context
def _format_dt_filter(ctx, value):
    return format_datetime(
        value,
        ctx.get("ui_datetime_format"),
        tz=ctx.get("ui_timezone"),
        lang=ctx.get("ui_lang"),
    )


def group_comments(comments) -> list[list]:
    groups: list[list] = []
    for comment in comments or []:
        if (
            groups
            and groups[-1][-1].author_id == comment.author_id
            and groups[-1][-1].is_internal == comment.is_internal
        ):
            groups[-1].append(comment)
        else:
            groups.append([comment])
    return groups


_templates.env.filters["format_dt"] = _format_dt_filter
_templates.env.filters["format_phone"] = format_phone
_templates.env.filters["group_comments"] = group_comments
_templates.env.filters["project_path"] = project_path
_templates.env.filters["ticket_path"] = ticket_path
_templates.env.filters["ticket_label"] = ticket_label
_templates.env.filters["admin_project_path"] = admin_project_path
_templates.env.filters["attachment_path"] = attachment_path
_templates.env.filters["user_initials"] = user_initials
_templates.env.filters["avatar_tone"] = avatar_tone
_templates.env.filters["markdown_safe"] = render_markdown_safe
_templates.env.globals["static_url"] = static_url
_templates.env.globals["field_attrs"] = field_attrs
_templates.env.globals["build_feed_path"] = build_feed_path


def _enum_label_map(lang: str, group: str, enum_cls: type[Enum]) -> dict:
    flat = translations_prefix(lang, f"enums.{group}")
    return {member: flat.get(member.value, member.value) for member in enum_cls}


def _theme_choices(lang: str):
    return [
        SimpleNamespace(
            id=theme.id,
            preview=theme.preview,
            label=t(lang, f"themes.{theme.id}.label"),
            description=t(lang, f"themes.{theme.id}.description"),
        )
        for theme in THEME_CHOICES
    ]


def _appearance_choices(lang: str, group: str, choices):
    return [
        SimpleNamespace(
            id=choice.id,
            label=t(lang, f"themes.{group}.{choice.id}.label"),
            description=t(lang, f"themes.{group}.{choice.id}.description"),
        )
        for choice in choices
    ]


def common_context(request: Request, **extra) -> dict:
    settings = get_settings()
    portal = get_portal_settings()
    lang = resolve_lang(request)
    ctx = {
        "request": request,
        "app_name": "PulseDeck",
        "csrf_token": ensure_csrf_token(request),
        "app_base_url": settings.app_base_url,
        "is_dev": settings.environment == "dev",
        "ui_lang": lang,
        "lang_choices": list_languages(),
        "lang_storage_key": LANG_STORAGE_KEY,
        "ui_theme": DEFAULT_THEME,
        "ui_scheme": theme_scheme(DEFAULT_THEME),
        "dark_theme_ids": [dark for _, dark in THEME_PAIRS],
        "theme_choices": _theme_choices(lang),
        "theme_storage_key": THEME_STORAGE_KEY,
        "ui_theme_gradient": DEFAULT_THEME_GRADIENT,
        "theme_gradient_storage_key": THEME_GRADIENT_STORAGE_KEY,
        "ui_density": DEFAULT_DENSITY,
        "density_choices": _appearance_choices(lang, "density", DENSITY_CHOICES),
        "density_storage_key": DENSITY_STORAGE_KEY,
        "ui_font_size": DEFAULT_FONT_SIZE,
        "font_size_choices": _appearance_choices(lang, "font_size", FONT_SIZE_CHOICES),
        "font_size_storage_key": FONT_SIZE_STORAGE_KEY,
        "ui_thread_order": DEFAULT_THREAD_ORDER,
        "thread_order_ids": list(THREAD_ORDER_IDS),
        "thread_order_storage_key": THREAD_ORDER_STORAGE_KEY,
        "ui_datetime_format": DEFAULT_DATETIME_FORMAT,
        "ui_timezone": DEFAULT_TIMEZONE,
        "datetime_prefs_locked": True,
        "datetime_format_choices": (),
        "timezone_choices": (),
        "ticket_types": TicketType,
        "ticket_statuses": TicketStatus,
        "ticket_priorities": TicketPriority,
        "user_roles": UserRole,
        "type_labels": _enum_label_map(lang, "ticket_type", TicketType),
        "status_labels": _enum_label_map(lang, "ticket_status", TicketStatus),
        "priority_labels": _enum_label_map(lang, "ticket_priority", TicketPriority),
        "role_labels": _enum_label_map(lang, "user_role", UserRole),
        "ticket_reopen_days": portal.ticket_reopen_days,
        "upload_max_files": max(1, portal.upload_max_files),
        "password_min_len": settings.password_min_len,
        "js_i18n": translations_prefix(lang, "js"),
    }

    def _t(message_key: str, **kwargs) -> str:
        return t(lang, message_key, **kwargs)

    ctx["t"] = _t
    ctx.update(extra)
    user = ctx.get("user")
    if user is not None:
        ui_tz = normalize_timezone(user.timezone)
        ui_fmt = normalize_datetime_format(user.datetime_format)
        ctx["ui_timezone"] = ui_tz
        ctx["ui_datetime_format"] = ui_fmt
        ctx["datetime_prefs_locked"] = bool(user.datetime_prefs_locked)
        if ctx.get("profile_section") == "profile":
            ctx["datetime_format_choices"] = list_datetime_formats(lang, tz=ui_tz)
            ctx["timezone_choices"] = list_timezones(current=ui_tz)
    return ctx


def render(request: Request, name: str, *, status_code: int = 200, **extra):
    ctx = common_context(request, **extra)
    if ctx.get("is_dev"):
        try:
            ctx["dev_page_info"] = build_dev_page_info(
                request, _templates.env, name, list(extra.keys())
            )
        except Exception:
            logger.exception("Dev page info failed for template %s", name)
            ctx["dev_page_info"] = None
    return _templates.TemplateResponse(request, name, ctx, status_code=status_code)


def request_lang(request: Request) -> str:
    return resolve_lang(request)


def default_lang() -> str:
    return (
        DEFAULT_LANG
        if DEFAULT_LANG in {c.id for c in list_languages()}
        else resolve_lang()
    )
