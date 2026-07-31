"""Rejestracja modeli SQLAlchemy."""

from app.models.email_outbox import EmailOutbox
from app.models.enums import (
    EmailOutboxPriority,
    EmailOutboxStatus,
    TicketPriority,
    TicketStatus,
    TicketType,
    UserRole,
)
from app.models.ticket import (
    Attachment,
    Comment,
    MagicToken,
    Tag,
    Ticket,
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
    "Project",
    "ProjectMember",
    "Tag",
    "Ticket",
    "TicketParticipant",
    "TicketPriority",
    "TicketStatus",
    "TicketTag",
    "TicketType",
    "User",
    "UserRole",
]
