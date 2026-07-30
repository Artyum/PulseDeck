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


class MagicTokenPurpose(str, enum.Enum):
    EMAIL_CONFIRM = "email_confirm"
    PASSWORD_SET = "password_set"
