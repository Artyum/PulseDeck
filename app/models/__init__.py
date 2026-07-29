"""Rejestracja modeli SQLAlchemy."""

from app.models.enums import TicketPriority, TicketStatus, TicketType, UserRole
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
