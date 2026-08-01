from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.ticket import Attachment, Ticket
    from app.models.user import Project


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
