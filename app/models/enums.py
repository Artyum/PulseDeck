from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    USER = "USER"
    STAFF = "STAFF"
    ADMIN = "ADMIN"


class TicketType(str, enum.Enum):
    BUG = "BUG"
    QUESTION = "QUESTION"
    SUGGESTION = "SUGGESTION"
    OTHER = "OTHER"


class TicketStatus(str, enum.Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_ON_CLIENT = "WAITING_ON_CLIENT"
    DONE = "DONE"


class TicketPriority(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


TICKET_TYPE_LABELS: dict[TicketType, str] = {
    TicketType.BUG: "Błąd",
    TicketType.QUESTION: "Pytanie",
    TicketType.SUGGESTION: "Sugestia",
    TicketType.OTHER: "Inne",
}

TICKET_STATUS_LABELS: dict[TicketStatus, str] = {
    TicketStatus.NEW: "Nowe",
    TicketStatus.IN_PROGRESS: "W obsłudze",
    TicketStatus.WAITING_ON_CLIENT: "Oczekuje na klienta",
    TicketStatus.DONE: "Zakończone",
}

TICKET_PRIORITY_LABELS: dict[TicketPriority, str] = {
    TicketPriority.LOW: "Niski",
    TicketPriority.NORMAL: "Normalny",
    TicketPriority.HIGH: "Wysoki",
}

USER_ROLE_LABELS: dict[UserRole, str] = {
    UserRole.USER: "Klient",
    UserRole.STAFF: "Obsługa",
    UserRole.ADMIN: "Administrator",
}


class MagicTokenPurpose(str, enum.Enum):
    EMAIL_CONFIRM = "email_confirm"
    PASSWORD_SET = "password_set"
