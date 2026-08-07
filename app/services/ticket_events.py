from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import TicketEventType
from app.models.ticket import Ticket, TicketEvent
from app.models.user import User
from app.utils.i18n import DEFAULT_LANG, t

_STAFF_ONLY_TYPES = frozenset(
    {
        TicketEventType.COMMENT_ADDED_INTERNAL,
        TicketEventType.COMMENT_EDITED_INTERNAL,
        TicketEventType.COMMENT_DELETED_INTERNAL,
    }
)

_ENUM_KIND = {
    TicketEventType.STATUS_CHANGED: "status",
    TicketEventType.PRIORITY_CHANGED: "priority",
    TicketEventType.TYPE_CHANGED: "type",
}

_NAMED = frozenset(
    {
        TicketEventType.TAG_ADDED,
        TicketEventType.TAG_REMOVED,
        TicketEventType.ATTACHMENT_ADDED,
        TicketEventType.ATTACHMENT_REMOVED,
        TicketEventType.PARTICIPANT_ADDED,
        TicketEventType.PARTICIPANT_REMOVED,
    }
)

_USER_PAIR = frozenset(
    {
        TicketEventType.ASSIGNEE_CHANGED,
        TicketEventType.REPORTER_CHANGED,
    }
)


@dataclass(frozen=True)
class FormattedTicketEvent:
    event: TicketEvent
    summaries: list[str]
    actor_name: str


def record_ticket_event(
    db: Session,
    ticket_id: int,
    actor_id: int | None,
    event_type: TicketEventType,
    payload: dict[str, Any] | None = None,
) -> TicketEvent:
    row = TicketEvent(
        ticket_id=ticket_id,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(row)
    return row


def log_enum_change(
    db: Session,
    ticket_id: int,
    actor_id: int | None,
    event_type: TicketEventType,
    old: Enum | None,
    new: Enum | None,
) -> None:
    if old == new:
        return
    record_ticket_event(
        db,
        ticket_id,
        actor_id,
        event_type,
        {
            "from": old.value if old is not None else None,
            "to": new.value if new is not None else None,
        },
    )


def log_user_change(
    db: Session,
    ticket_id: int,
    actor_id: int | None,
    event_type: TicketEventType,
    from_id: int | None,
    to_id: int | None,
) -> None:
    if from_id == to_id:
        return
    record_ticket_event(
        db,
        ticket_id,
        actor_id,
        event_type,
        {"from_id": from_id, "to_id": to_id},
    )


def list_ticket_events(
    db: Session,
    ticket: Ticket,
    *,
    staff: bool,
) -> list[TicketEvent]:
    rows = list(
        db.scalars(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket.id)
            .options(selectinload(TicketEvent.actor))
            .order_by(TicketEvent.created_at.desc(), TicketEvent.id.desc())
        ).all()
    )
    if staff:
        return rows
    return [ev for ev in rows if ev.event_type not in _STAFF_ONLY_TYPES]


def _same_batch(a: TicketEvent, b: TicketEvent) -> bool:
    if a.actor_id != b.actor_id:
        return False
    if a.created_at is not None and a.created_at == b.created_at:
        return True
    if a.id is None or b.id is None:
        return False
    if abs(a.id - b.id) != 1:
        return False
    if a.created_at is None or b.created_at is None:
        return True
    return abs((a.created_at - b.created_at).total_seconds()) < 1


def _group_events(events: list[TicketEvent]) -> list[list[TicketEvent]]:
    groups: list[list[TicketEvent]] = []
    for ev in events:
        if groups and _same_batch(groups[-1][-1], ev):
            groups[-1].append(ev)
        else:
            groups.append([ev])
    for group in groups:
        group.sort(key=lambda row: row.id)
    return groups


def _enum_label(lang: str, kind: str, value: str | None) -> str:
    if not value:
        return t(lang, "ui.ticket.assignee_none")
    return t(lang, f"enums.ticket_{kind}.{value}")


def _user_label(
    db: Session, lang: str, user_id: int | None, cache: dict[int, str]
) -> str:
    if user_id is None:
        return t(lang, "ui.ticket.assignee_none")
    cached = cache.get(user_id)
    if cached is not None:
        return cached
    user = db.get(User, user_id)
    name = user.display_name if user else t(lang, "ui.ticket.history_unknown_user")
    cache[user_id] = name
    return name


def format_event_summary(
    db: Session,
    event: TicketEvent,
    *,
    lang: str,
    user_cache: dict[int, str],
) -> str:
    payload = event.payload or {}
    et = event.event_type
    key = f"ui.ticket.event.{et.value}"

    if et == TicketEventType.CREATED:
        return t(
            lang,
            key,
            type=_enum_label(lang, "type", payload.get("type")),
            priority=_enum_label(lang, "priority", payload.get("priority")),
        )
    if et in _ENUM_KIND:
        kind = _ENUM_KIND[et]
        return t(
            lang,
            key,
            **{
                "from": _enum_label(lang, kind, payload.get("from")),
                "to": _enum_label(lang, kind, payload.get("to")),
            },
        )
    if et in _USER_PAIR:
        return t(
            lang,
            key,
            **{
                "from": _user_label(db, lang, payload.get("from_id"), user_cache),
                "to": _user_label(db, lang, payload.get("to_id"), user_cache),
            },
        )
    if et in _NAMED:
        if et in (
            TicketEventType.PARTICIPANT_ADDED,
            TicketEventType.PARTICIPANT_REMOVED,
        ):
            name = _user_label(db, lang, payload.get("user_id"), user_cache)
        else:
            name = payload.get("tag_name") or payload.get("file_name") or ""
        return t(lang, key, name=name)
    return t(lang, key)


def format_ticket_events(
    db: Session,
    events: list[TicketEvent],
    *,
    lang: str | None = None,
) -> list[FormattedTicketEvent]:
    lang = lang or DEFAULT_LANG
    cache: dict[int, str] = {}
    out: list[FormattedTicketEvent] = []
    for group in _group_events(events):
        lead = group[0]
        actor_name = (
            lead.actor.display_name
            if lead.actor
            else t(lang, "ui.ticket.history_unknown_user")
        )
        out.append(
            FormattedTicketEvent(
                event=lead,
                summaries=[
                    format_event_summary(db, ev, lang=lang, user_cache=cache)
                    for ev in group
                ],
                actor_name=actor_name,
            )
        )
    return out
