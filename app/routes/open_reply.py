from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.deps.auth import DbSession, get_optional_user
from app.models.ticket import Attachment, Comment, Ticket
from app.models.user import User
from app.rate_limit import client_ip_key, limiter
from app.routes.context import render
from app.services import reply_token as reply_token_service
from app.services import tickets as ticket_service
from app.services.auth import hash_magic_token
from app.services.email import notify_new_comment
from app.services.reply_token import ReplyTokenStatus
from app.services.uploads import file_response_for_attachment, save_upload
from app.utils.i18n import resolve_lang, t
from app.utils.urls import ticket_path

router = APIRouter(tags=["reply-token"])

_MAX_ATTACHMENTS = 3
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
    return render(
        request,
        "reply/thread.html",
        token=token,
        user=user,
        ticket=ticket,
        project=ticket.project,
        file_urls=reply_token_service.attachment_file_urls(ticket, user),
        can_comment=ticket_service.can_comment(db, user, ticket),
        error=error,
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


def _conflict_page(request: Request, session_user: User, owner: User | None):
    return render(
        request,
        "reply/conflict.html",
        session_email=session_user.email,
        owner_email=owner.email if owner else "",
    )


async def _attach_many(
    db: Session,
    attachments: list[UploadFile] | None,
    *,
    ticket_id: int,
    comment_id: int,
    lang: str,
) -> None:
    if not attachments:
        return
    count = 0
    for attachment in attachments:
        if count >= _MAX_ATTACHMENTS:
            break
        if not attachment or not attachment.filename:
            continue
        original, rel = await save_upload(
            attachment, subdir=f"tickets/{ticket_id}", lang=lang
        )
        ticket_service.add_attachment(
            db,
            file_name=original,
            file_path=rel,
            ticket_id=None,
            comment_id=comment_id,
            commit=False,
        )
        count += 1


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
        return _conflict_page(request, session_user, owner)

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
async def open_reply_post(
    request: Request,
    token: str,
    db: DbSession,
    content: Annotated[str, Form()] = "",
    attachments: Annotated[list[UploadFile] | None, File()] = None,
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
        return _conflict_page(request, session_user, db.get(User, row.user_id))

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
    text = (content or "").strip()
    if not text:
        return _thread_page(
            request,
            db,
            token=token,
            user=owner,
            ticket=ticket,
            error=t(lang, "messages.tickets.comment_empty"),
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
        comment = ticket_service.add_comment(
            db, ticket, owner, text, is_internal=False, lang=lang, commit=False
        )
        await _attach_many(
            db,
            attachments,
            ticket_id=ticket.id,
            comment_id=comment.id,
            lang=lang,
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

    notify_new_comment(db, ticket, owner.id, is_internal=False)
    _log(
        request,
        "success",
        user_id=owner.id,
        token_id=locked.id,
        raw=token,
        ticket_id=ticket.id,
    )
    return _status_page(request, "thanks")


@router.get("/reply-file/{attachment_id}")
@limiter.limit(_get_limit)
def reply_file_download(
    request: Request,
    attachment_id: int,
    db: DbSession,
    exp: int = 0,
    sig: str = "",
    ticket_id: int = 0,
):
    lang = resolve_lang(request)
    if not reply_token_service.verify_reply_file_sig(
        attachment_id, ticket_id=ticket_id, exp=exp, sig=sig
    ):
        raise HTTPException(status_code=403, detail=t(lang, "messages.http.forbidden"))

    att = db.scalar(
        select(Attachment)
        .where(Attachment.id == attachment_id)
        .options(
            joinedload(Attachment.ticket),
            joinedload(Attachment.comment).joinedload(Comment.ticket),
        )
    )
    ticket = None
    if att is not None:
        ticket = att.ticket if att.comment is None else att.comment.ticket
    if att is None or ticket is None or ticket.id != ticket_id:
        raise HTTPException(status_code=404, detail=t(lang, "messages.http.not_found"))
    return file_response_for_attachment(att, lang=lang)
