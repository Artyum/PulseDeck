from __future__ import annotations

from app.models.enums import TicketPriority, TicketStatus, TicketType, UserRole
from app.utils.i18n import available_lang_ids
from app.utils.timefmt import DATETIME_FORMAT_IDS
from app.validation.spec import (
    email,
    enum_field,
    key,
    password,
    phone,
    text,
    timezone,
)


def _lang_values() -> frozenset[str]:
    langs = available_lang_ids()
    return langs if langs else frozenset({"en"})


FIELDS = {
    "user.email": email(),
    "user.password": password(),
    "user.first_name": text(max_len=120),
    "user.last_name": text(max_len=120),
    "user.phone": phone(),
    "user.role": enum_field(UserRole),
    "user.ui_lang": enum_field(_lang_values()),
    "user.datetime_format": enum_field(frozenset(DATETIME_FORMAT_IDS)),
    "user.timezone": timezone(),
    "project.name": text(max_len=200),
    "project.key": key(),
    "project.description": text(required=False, max_len=2000),
    "ticket.title": text(max_len=300),
    "ticket.description": text(max_len=10000),
    "ticket.type": enum_field(TicketType),
    "ticket.status": enum_field(TicketStatus),
    "ticket.priority": enum_field(TicketPriority),
    "comment.content": text(max_len=10000),
    "tag.name": text(max_len=80, collapse_spaces=True),
    "search.q": text(required=False, max_len=200),
    "filter.tag": text(required=False, max_len=80),
}
