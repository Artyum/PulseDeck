"""Rejestracja modeli SQLAlchemy."""

from app.models.email_outbox import EmailOutbox
from app.models.enums import (
    EmailOutboxPriority,
    EmailOutboxStatus,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    TicketType,
    UserRole,
)
from app.models.portal_settings import PortalSetting
from app.models.ticket import (
    Attachment,
    Comment,
    MagicToken,
    Tag,
    Ticket,
    TicketEvent,
    TicketParticipant,
    TicketTag,
)
from app.models.user import Project, ProjectMember, User

__all__ = [
    "Attachment",
    "Comment",
    "EmailOutbox",
    "EmailOutboxPriority",
    "EmailOutboxStatus",
    "MagicToken",
    "PortalSetting",
    "Project",
    "ProjectMember",
    "Tag",
    "Ticket",
    "TicketEvent",
    "TicketEventType",
    "TicketParticipant",
    "TicketPriority",
    "TicketStatus",
    "TicketTag",
    "TicketType",
    "User",
    "UserRole",
]
