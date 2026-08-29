from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    USER = "USER"
    STAFF = "STAFF"
    ADMIN = "ADMIN"


class TicketType(str, enum.Enum):
    BUG = "BUG"
    QUESTION = "QUESTION"
    CHANGE = "CHANGE"
    TASK = "TASK"


class TicketStatus(str, enum.Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_ON_CLIENT = "WAITING_ON_CLIENT"
    DONE = "DONE"


class TicketPriority(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class TicketEventType(str, enum.Enum):
    CREATED = "CREATED"
    COMMENT_ADDED = "COMMENT_ADDED"
    COMMENT_ADDED_INTERNAL = "COMMENT_ADDED_INTERNAL"
    COMMENT_EDITED = "COMMENT_EDITED"
    COMMENT_EDITED_INTERNAL = "COMMENT_EDITED_INTERNAL"
    COMMENT_DELETED = "COMMENT_DELETED"
    COMMENT_DELETED_INTERNAL = "COMMENT_DELETED_INTERNAL"
    TITLE_CHANGED = "TITLE_CHANGED"
    DESCRIPTION_CHANGED = "DESCRIPTION_CHANGED"
    STATUS_CHANGED = "STATUS_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    TYPE_CHANGED = "TYPE_CHANGED"
    ASSIGNEE_CHANGED = "ASSIGNEE_CHANGED"
    REPORTER_CHANGED = "REPORTER_CHANGED"
    PARTICIPANT_ADDED = "PARTICIPANT_ADDED"
    PARTICIPANT_REMOVED = "PARTICIPANT_REMOVED"
    TAG_ADDED = "TAG_ADDED"
    TAG_REMOVED = "TAG_REMOVED"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    ATTACHMENT_REMOVED = "ATTACHMENT_REMOVED"
    DELETED = "DELETED"


class MagicTokenPurpose(str, enum.Enum):
    EMAIL_CONFIRM = "email_confirm"
    PASSWORD_SET = "password_set"
    TICKET_REPLY = "ticket_reply"


class EmailOutboxPriority(str, enum.Enum):
    AUTH = "auth"
    TICKET = "ticket"


class EmailOutboxStatus(str, enum.Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
