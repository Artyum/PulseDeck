from __future__ import annotations

import logging

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import get_settings, project_root
from app.models.enums import (
    TICKET_PRIORITY_LABELS,
    TICKET_STATUS_LABELS,
    TICKET_TYPE_LABELS,
    USER_ROLE_LABELS,
    TicketPriority,
    TicketStatus,
    TicketType,
    UserRole,
)
from app.utils.csrf import ensure_csrf_token
from app.utils.dev_page_info import build_dev_page_info
from app.utils.themes import (
    DEFAULT_DENSITY,
    DEFAULT_FONT_SIZE,
    DEFAULT_THEME,
    DENSITY_CHOICES,
    DENSITY_STORAGE_KEY,
    FONT_SIZE_CHOICES,
    FONT_SIZE_STORAGE_KEY,
    THEME_CHOICES,
    THEME_STORAGE_KEY,
)
from app.utils.timefmt import age_since, gap_between
from app.utils.urls import admin_project_path, project_path, ticket_label, ticket_path

logger = logging.getLogger("pulsedeck.app")

_templates = Jinja2Templates(directory=str(project_root() / "frontend" / "templates"))
_templates.env.filters["age_since"] = age_since
_templates.env.filters["gap_between"] = gap_between
_templates.env.filters["project_path"] = project_path
_templates.env.filters["ticket_path"] = ticket_path
_templates.env.filters["ticket_label"] = ticket_label
_templates.env.filters["admin_project_path"] = admin_project_path


def common_context(request: Request, **extra) -> dict:
    settings = get_settings()
    ctx = {
        "request": request,
        "app_name": "PulseDeck",
        "csrf_token": ensure_csrf_token(request),
        "app_base_url": settings.app_base_url,
        "is_dev": settings.environment == "development",
        "ui_theme": DEFAULT_THEME,
        "theme_choices": THEME_CHOICES,
        "theme_storage_key": THEME_STORAGE_KEY,
        "ui_density": DEFAULT_DENSITY,
        "density_choices": DENSITY_CHOICES,
        "density_storage_key": DENSITY_STORAGE_KEY,
        "ui_font_size": DEFAULT_FONT_SIZE,
        "font_size_choices": FONT_SIZE_CHOICES,
        "font_size_storage_key": FONT_SIZE_STORAGE_KEY,
        "ticket_types": TicketType,
        "ticket_statuses": TicketStatus,
        "ticket_priorities": TicketPriority,
        "user_roles": UserRole,
        "type_labels": TICKET_TYPE_LABELS,
        "status_labels": TICKET_STATUS_LABELS,
        "priority_labels": TICKET_PRIORITY_LABELS,
        "role_labels": USER_ROLE_LABELS,
        "ticket_reopen_days": settings.ticket_reopen_days,
    }
    ctx.update(extra)
    return ctx


def render(request: Request, name: str, **extra):
    ctx = common_context(request, **extra)
    if ctx.get("is_dev"):
        try:
            ctx["dev_page_info"] = build_dev_page_info(
                request, _templates.env, name, list(extra.keys())
            )
        except Exception:
            logger.exception("Dev page info failed for template %s", name)
            ctx["dev_page_info"] = None
    return _templates.TemplateResponse(request, name, ctx)
