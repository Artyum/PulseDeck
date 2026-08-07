from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps.auth import DbSession, get_optional_user
from app.models.ticket import Ticket
from app.models.user import User
from app.rate_limit import client_ip_key, limiter
from app.routes.context import group_comments, render
from app.services import projects as project_service
from app.services import reply_token as reply_token_service
from app.services import tickets as ticket_service
from app.services.auth import hash_magic_token
from app.services.email import emit_comment
from app.services.reply_token import ReplyTokenStatus
from app.utils.i18n import resolve_lang
from app.utils.timefmt import normalize_datetime_format, normalize_timezone
from app.utils.urls import ticket_path
from app.validation import clean

router = APIRouter(tags=["reply-token"])

_REJECT_STATUSES = frozenset(
    {
        ReplyTokenStatus.INVALID,
        ReplyTokenStatus.USED,
        ReplyTokenStatus.EXPIRED,
    }
)


def _get_limit() -> str:
    return get_settings().reply_token_get_rate_limit


def _post_limit() -> str:
    return get_settings().reply_token_post_rate_limit


def _visible_comment_groups(user: User, ticket: Ticket, db: Session) -> list[list]:
    comments = list(ticket.comments or [])
    if not project_service.has_staff_capabilities(db, ticket.project_id, user):
        comments = [c for c in comments if not c.is_internal]
    return group_comments(comments)


def _log(
    request: Request,
    result: str,
    *,
    user_id: int | None = None,
    token_id: int | None = None,
    raw: str | None = None,
    ticket_id: int | None = None,
) -> None:
    reply_token_service.log_reply_token_event(
        result=result,
        user_id=user_id,
        token_id=token_id,
        token_hash=hash_magic_token(raw) if raw else None,
        ticket_id=ticket_id,
        ip=client_ip_key(request),
        ua=request.headers.get("user-agent"),
    )


def _status_page(request: Request, status_key: str):
    return render(request, "reply/status.html", status_key=status_key)


def _thread_page(
    request: Request,
    db: Session,
    *,
    token: str,
    user: User,
    ticket: Ticket,
    error: str | None = None,
):
    groups = _visible_comment_groups(user, ticket, db)
    visible_group = groups[-1] if groups else []
    return render(
        request,
        "reply/thread.html",
        token=token,
        ticket=ticket,
        project=ticket.project,
        comment_groups=[visible_group] if visible_group else [],
        has_earlier_messages=len(groups) > 1,
        can_comment=ticket_service.can_comment(db, user, ticket),
        error=error,
        ui_timezone=normalize_timezone(user.timezone),
        ui_datetime_format=normalize_datetime_format(user.datetime_format),
    )


def _reject_unusable(
    request: Request,
    token: str,
    row,
    status: ReplyTokenStatus,
):
    if status not in _REJECT_STATUSES:
        return None
    _log(
        request,
        status.value,
        user_id=row.user_id if row else None,
        token_id=row.id if row else None,
        raw=token,
        ticket_id=row.ticket_id if row else None,
    )
    return _status_page(request, status.value)


def _conflict_page(request: Request):
    return render(request, "reply/conflict.html")


@router.get("/open/{token}", response_class=HTMLResponse)
@limiter.limit(_get_limit)
def open_reply_get(request: Request, token: str, db: DbSession):
    row = reply_token_service.lookup_reply_token(db, token)
    status = reply_token_service.classify_reply_token(row)
    rejected = _reject_unusable(request, token, row, status)
    if rejected is not None:
        return rejected

    assert row is not None
    ctx = reply_token_service.load_reply_context(db, row)
    if not ctx:
        _log(
            request,
            "forbidden",
            user_id=row.user_id,
            token_id=row.id,
            raw=token,
            ticket_id=row.ticket_id,
        )
        return _status_page(request, "forbidden")

    owner, ticket = ctx
    session_user = get_optional_user(request, db)

    if session_user and session_user.id == owner.id:
        _log(
            request,
            "owner_redirect",
            user_id=owner.id,
            token_id=row.id,
            raw=token,
            ticket_id=ticket.id,
        )
        return RedirectResponse(ticket_path(ticket), status_code=303)

    if session_user and session_user.id != owner.id:
        _log(
            request,
            "session_conflict",
            user_id=session_user.id,
            token_id=row.id,
            raw=token,
            ticket_id=ticket.id,
        )
        return _conflict_page(request)

    _log(
        request,
        "ok",
        user_id=owner.id,
        token_id=row.id,
        raw=token,
        ticket_id=ticket.id,
    )
    return _thread_page(request, db, token=token, user=owner, ticket=ticket)


@router.post("/open/{token}", response_class=HTMLResponse)
@limiter.limit(_post_limit)
def open_reply_post(
    request: Request,
    token: str,
    db: DbSession,
    content: Annotated[str, Form()] = "",
):
    lang = resolve_lang(request)
    row = reply_token_service.lookup_reply_token(db, token)
    status = reply_token_service.classify_reply_token(row)
    rejected = _reject_unusable(request, token, row, status)
    if rejected is not None:
        return rejected

    assert row is not None
    session_user = get_optional_user(request, db)
    if session_user and session_user.id != row.user_id:
        return _conflict_page(request)

    ctx = reply_token_service.load_reply_context(db, row)
    if not ctx:
        _log(
            request,
            "forbidden",
            user_id=row.user_id,
            token_id=row.id,
            raw=token,
            ticket_id=row.ticket_id,
        )
        return _status_page(request, "forbidden")

    owner, ticket = ctx
    try:
        text = clean("comment.content", content or "", lang=lang)
    except ValueError as exc:
        return _thread_page(
            request,
            db,
            token=token,
            user=owner,
            ticket=ticket,
            error=str(exc),
        )

    locked = reply_token_service.lock_reply_token(db, row.id)
    if (
        locked is None
        or reply_token_service.classify_reply_token(locked) != ReplyTokenStatus.OK
    ):
        db.rollback()
        _log(
            request,
            "used",
            user_id=row.user_id,
            token_id=row.id,
            raw=token,
            ticket_id=row.ticket_id,
        )
        return _status_page(request, "used")

    try:
        ticket_service.add_comment(
            db, ticket, owner, text, is_internal=False, lang=lang, commit=False
        )
        reply_token_service.consume_reply_token(locked)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        if exc.status_code == 403:
            _log(
                request,
                "forbidden",
                user_id=owner.id,
                token_id=locked.id,
                raw=token,
                ticket_id=ticket.id,
            )
            return _status_page(request, "forbidden")
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        ticket = ticket_service.get_ticket(db, ticket.id) or ticket
        return _thread_page(
            request, db, token=token, user=owner, ticket=ticket, error=detail
        )
    except Exception:
        db.rollback()
        raise

    emit_comment(db, ticket, owner.id, is_internal=False)
    _log(
        request,
        "success",
        user_id=owner.id,
        token_id=locked.id,
        raw=token,
        ticket_id=ticket.id,
    )
    return _status_page(request, "thanks")
