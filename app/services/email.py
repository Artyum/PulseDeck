from __future__ import annotations

import logging
import smtplib
from collections.abc import Iterable
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import partial

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings, project_root
from app.models.email_outbox import EmailOutbox
from app.models.enums import EmailOutboxPriority, EmailOutboxStatus, UserRole
from app.models.ticket import Ticket, TicketParticipant
from app.models.user import ProjectMember, User
from app.services import projects as project_service
from app.utils.i18n import DEFAULT_LANG, t
from app.utils.urls import ticket_path

logger = logging.getLogger("pulsedeck.services.email")

APP_NAME = "PulseDeck"

_env = Environment(
    loader=FileSystemLoader(str(project_root() / "app" / "templates" / "email")),
    autoescape=select_autoescape(["html", "xml"]),
)


def send_email_sync(to: str, subject: str, html_body: str) -> bool:
    settings = get_settings()
    if not settings.smtp_configured:
        logger.warning("SMTP not configured — skip email to %s subject=%s", to, subject)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from_address
    msg["To"] = to
    msg.set_content(html_body, subtype="html")
    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_server, settings.smtp_port, timeout=30
            ) as smtp:
                _smtp_auth(smtp, settings.smtp_user, settings.smtp_pass)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(
                settings.smtp_server, settings.smtp_port, timeout=30
            ) as smtp:
                smtp.ehlo()
                if smtp.has_extn("starttls"):
                    smtp.starttls()
                    smtp.ehlo()
                _smtp_auth(smtp, settings.smtp_user, settings.smtp_pass)
                smtp.send_message(msg)
        logger.info("Email sent to %s subject=%s", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


def _smtp_auth(smtp: smtplib.SMTP, user: str, password: str) -> None:
    if user.strip() and password:
        smtp.login(user, password)


def render_email_html(template: str, context: dict, *, lang: str = DEFAULT_LANG) -> str:
    return _env.get_template(template).render(
        **context,
        app_name=APP_NAME,
        ui_lang=lang,
        t=partial(t, lang),
    )


def enqueue_email(
    db: Session,
    *,
    to_email: str,
    subject: str,
    html_body: str,
    priority: EmailOutboxPriority = EmailOutboxPriority.TICKET,
) -> None:
    db.add(
        EmailOutbox(
            priority=priority,
            to_email=to_email.strip().lower(),
            subject=subject,
            html_body=html_body,
            status=EmailOutboxStatus.PENDING,
            available_at=datetime.now(timezone.utc),
        )
    )


def _enqueue_users(
    db: Session,
    recipients: Iterable[User],
    subject: str,
    template: str,
    context: dict,
    *,
    priority: EmailOutboxPriority = EmailOutboxPriority.TICKET,
    lang: str = DEFAULT_LANG,
) -> None:
    html = render_email_html(template, context, lang=lang)
    seen: set[str] = set()
    for user in recipients:
        email = (user.email or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        enqueue_email(
            db, to_email=email, subject=subject, html_body=html, priority=priority
        )
    if seen:
        db.commit()


def _enqueue_auth(
    db: Session,
    *,
    to_email: str,
    subject: str,
    template: str,
    context: dict,
    lang: str,
) -> None:
    enqueue_email(
        db,
        to_email=to_email,
        subject=subject,
        html_body=render_email_html(template, context, lang=lang),
        priority=EmailOutboxPriority.AUTH,
    )
    db.commit()


def _staff_circle(db: Session, ticket: Ticket) -> list[User]:
    member_staff = db.scalars(
        select(User)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(
            ProjectMember.project_id == ticket.project_id,
            User.role == UserRole.STAFF,
        )
    ).all()
    by_id = {u.id: u for u in (*project_service.list_admins(db), *member_staff)}
    if ticket.assignee:
        by_id[ticket.assignee.id] = ticket.assignee
    return list(by_id.values())


def _client_circle(ticket: Ticket) -> list[User]:
    by_id: dict[int, User] = {}
    if ticket.author and not ticket.author.is_staff:
        by_id[ticket.author.id] = ticket.author
    for p in ticket.participants:
        if p.user and not p.user.is_staff:
            by_id[p.user.id] = p.user
    return list(by_id.values())


def _pick(
    users: Iterable[User],
    *,
    exclude_id: int | None,
    pref: str,
) -> list[User]:
    out: list[User] = []
    for user in users:
        if exclude_id is not None and user.id == exclude_id:
            continue
        if not getattr(user, pref):
            continue
        out.append(user)
    return out


def _ticket_url(ticket: Ticket) -> str:
    settings = get_settings()
    try:
        return f"{settings.app_base_url}{ticket_path(ticket)}"
    except ValueError:
        return f"{settings.app_base_url}/"


def _load_ticket(db: Session, ticket_id: int) -> Ticket | None:
    return db.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.author),
            selectinload(Ticket.assignee),
            selectinload(Ticket.participants).selectinload(TicketParticipant.user),
            selectinload(Ticket.project),
        )
    )


def notify_email_confirm(
    db: Session,
    user: User,
    token: str,
    to_email: str,
    *,
    lang: str | None = None,
) -> None:
    lang = lang or DEFAULT_LANG
    settings = get_settings()
    _enqueue_auth(
        db,
        to_email=to_email,
        subject=t(lang, "email.confirm.subject", app=APP_NAME),
        template="email_confirm.html",
        context={
            "user": user,
            "url": f"{settings.app_base_url}/auth/confirm-email?token={token}",
            "ttl_minutes": settings.email_confirm_ttl_minutes,
        },
        lang=lang,
    )


def notify_password_set(
    db: Session,
    user: User,
    token: str,
    *,
    lang: str | None = None,
) -> None:
    lang = lang or DEFAULT_LANG
    settings = get_settings()
    activation = user.activated_at is None
    _enqueue_auth(
        db,
        to_email=user.email,
        subject=t(
            lang,
            "email.activate.subject" if activation else "email.reset.subject",
            app=APP_NAME,
        ),
        template="account_activate.html" if activation else "password_reset.html",
        context={
            "user": user,
            "url": f"{settings.app_base_url}/auth/activate?token={token}",
            "ttl_days": settings.auth_link_ttl_days,
        },
        lang=lang,
    )


def notify_new_ticket(db: Session, ticket: Ticket) -> None:
    if ticket.author and ticket.author.is_staff:
        return
    loaded = _load_ticket(db, ticket.id) or ticket
    recipients = _pick(
        _staff_circle(db, loaded),
        exclude_id=loaded.author_id,
        pref="notify_new_ticket",
    )
    if not recipients:
        return
    lang = DEFAULT_LANG
    _enqueue_users(
        db,
        recipients,
        t(lang, "email.new_ticket.subject", title=loaded.title),
        "new_ticket.html",
        {"ticket": loaded, "url": _ticket_url(loaded)},
        lang=lang,
    )


def notify_new_comment(
    db: Session,
    ticket: Ticket,
    author_id: int,
    *,
    is_internal: bool = False,
) -> None:
    if is_internal:
        return
    loaded = _load_ticket(db, ticket.id) or ticket
    author = db.get(User, author_id)
    circle = (
        _client_circle(loaded)
        if author and author.is_staff
        else _staff_circle(db, loaded)
    )
    recipients = _pick(circle, exclude_id=author_id, pref="notify_reply")
    if not recipients:
        return
    lang = DEFAULT_LANG
    _enqueue_users(
        db,
        recipients,
        t(lang, "email.new_comment.subject", title=loaded.title),
        "new_comment.html",
        {"ticket": loaded, "url": _ticket_url(loaded)},
        lang=lang,
    )


def notify_ticket_update(
    db: Session, ticket: Ticket, actor_id: int, *, change_label: str
) -> None:
    loaded = _load_ticket(db, ticket.id) or ticket
    by_id = {u.id: u for u in (*_staff_circle(db, loaded), *_client_circle(loaded))}
    recipients = _pick(
        by_id.values(), exclude_id=actor_id, pref="notify_ticket_update"
    )
    if not recipients:
        return
    lang = DEFAULT_LANG
    _enqueue_users(
        db,
        recipients,
        t(lang, "email.ticket_update.subject", title=loaded.title),
        "ticket_update.html",
        {
            "ticket": loaded,
            "url": _ticket_url(loaded),
            "change_label": change_label,
        },
        lang=lang,
    )


def notify_assignment(
    db: Session,
    ticket: Ticket,
    *,
    actor_id: int,
    previous: User | None,
    new: User | None,
) -> None:
    targets: list[tuple[User, str]] = []
    if new is not None and new.id != actor_id:
        targets.append((new, "assignment"))
    if (
        previous is not None
        and previous.id != actor_id
        and (new is None or previous.id != new.id)
    ):
        targets.append((previous, "unassignment"))
    if not targets:
        return
    lang = DEFAULT_LANG
    url = _ticket_url(ticket)
    for user, key in targets:
        enqueue_email(
            db,
            to_email=user.email,
            subject=t(lang, f"email.{key}.subject", title=ticket.title),
            html_body=render_email_html(
                f"{key}.html",
                {"ticket": ticket, "url": url, "assignee": user},
                lang=lang,
            ),
        )
    db.commit()
