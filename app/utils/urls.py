from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

if TYPE_CHECKING:
    from app.models.ticket import Attachment, Ticket
    from app.models.user import Project

FEED_PER_PAGE_DEFAULT = 25


def project_path(project: Project) -> str:
    return f"/p/{project.key}"


def ticket_label(ticket: Ticket) -> str:
    key = ticket.project.key if ticket.project else None
    if not key:
        raise ValueError("ticket.project.key is required for ticket_label")
    return f"{key}-{ticket.number}"


def ticket_path(ticket: Ticket) -> str:
    return f"/t/{ticket_label(ticket)}"


def admin_project_path(project: Project) -> str:
    return f"/admin/projects/{project.key}"


def attachment_path(attachment: Attachment) -> str:
    return f"/files/{attachment.id}"


def safe_next_path(value: str | None, *, default: str = "/") -> str:
    if not value:
        return default
    path = value.strip()
    if not path.startswith("/") or path.startswith("//"):
        return default
    if any(c in path for c in ("\\", "\n", "\r", "\0")):
        return default
    if "://" in path:
        return default
    return path


def normalize_project_key(key: str) -> str:
    return (key or "").strip().upper()


def default_feed_path(key: str) -> str:
    clean = normalize_project_key(key)
    return f"/p/{clean}?view=all&mine=1"


def build_feed_path(
    key: str,
    *,
    view: str | None = None,
    mine: bool = False,
    mine_paused: bool = False,
    priority: str | None = None,
    type: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    page: int | None = None,
    per_page: int | None = None,
) -> str:
    clean = normalize_project_key(key)
    params: list[tuple[str, str]] = []
    if view:
        params.append(("view", view))
    if mine:
        params.append(("mine", "1"))
    elif mine_paused:
        params.append(("mine_paused", "1"))
    if priority:
        params.append(("priority", priority))
    if type:
        params.append(("type", type))
    if status:
        params.append(("status", status))
    if tag:
        params.append(("tag", tag))
    if q:
        params.append(("q", q))
    if sort and sort != "created_at":
        params.append(("sort", sort))
    if page is not None and page > 1:
        params.append(("page", str(page)))
    if per_page is not None and per_page != FEED_PER_PAGE_DEFAULT:
        params.append(("per_page", str(per_page)))
    base = f"/p/{clean}"
    if not params:
        return base
    return f"{base}?{urlencode(params)}"


def validate_feed_path(path: str | None, key: str) -> str | None:
    clean = normalize_project_key(key)
    if not clean or not path:
        return None
    safe = safe_next_path(path, default="")
    if not safe:
        return None
    prefix = f"/p/{clean}"
    if safe == prefix or safe.startswith(f"{prefix}?"):
        return safe
    return None
