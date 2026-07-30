from __future__ import annotations

import logging
import smtplib
from collections.abc import Iterable
from email.message import EmailMessage
from functools import partial

from fastapi import BackgroundTasks
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings, project_root
from app.models.enums import UserRole
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


def _send_email_sync(to: str, subject: str, html_body: str) -> bool:
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


def queue_email(
    background: BackgroundTasks,
    to: str,
    subject: str,
    template: str,
    context: dict,
    *,
    lang: str = DEFAULT_LANG,
) -> None:
    html = _env.get_template(template).render(
        **context,
        app_name=APP_NAME,
        ui_lang=lang,
        t=partial(t, lang),
    )
    background.add_task(_send_email_sync, to, subject, html)


def _broadcast(
    background: BackgroundTasks,
    recipients: Iterable[str],
    subject: str,
    template: str,
    context: dict,
    *,
    lang: str = DEFAULT_LANG,
) -> None:
    for email in sorted(set(recipients)):
        queue_email(background, email, subject, template, context, lang=lang)


def notify_email_confirm(
    background: BackgroundTasks,
    user: User,
    token: str,
    to_email: str,
    *,
    lang: str | None = None,
) -> None:
    lang = lang or DEFAULT_LANG
    settings = get_settings()
    url = f"{settings.app_base_url}/auth/confirm-email?token={token}"
    queue_email(
        background,
        to_email,
        t(lang, "email.confirm.subject", app=APP_NAME),
        "email_confirm.html",
        {
            "user": user,
            "url": url,
            "ttl_minutes": settings.email_confirm_ttl_minutes,
        },
        lang=lang,
    )


def notify_password_set(
    background: BackgroundTasks,
    user: User,
    token: str,
    *,
    lang: str | None = None,
) -> None:
    lang = lang or DEFAULT_LANG
    settings = get_settings()
    url = f"{settings.app_base_url}/auth/activate?token={token}"
    is_activation = user.activated_at is None
    if is_activation:
        subject = t(lang, "email.activate.subject", app=APP_NAME)
        template = "account_activate.html"
    else:
        subject = t(lang, "email.reset.subject", app=APP_NAME)
        template = "password_reset.html"
    queue_email(
        background,
        user.email,
        subject,
        template,
        {
            "user": user,
            "url": url,
            "ttl_days": settings.auth_link_ttl_days,
        },
        lang=lang,
    )


def staff_emails_for_project(db: Session, project_id: int) -> list[str]:
    member_staff = db.scalars(
        select(User)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(
            ProjectMember.project_id == project_id,
            User.role == UserRole.STAFF,
        )
    ).all()
    admins = project_service.list_admins(db)
    return list(dict.fromkeys(u.email for u in (*admins, *member_staff)))


def _ticket_url(ticket: Ticket) -> str:
    settings = get_settings()
    try:
        return f"{settings.app_base_url}{ticket_path(ticket)}"
    except ValueError:
        return f"{settings.app_base_url}/"


def notify_new_ticket(background: BackgroundTasks, db: Session, ticket: Ticket) -> None:
    url = _ticket_url(ticket)
    author_email = ticket.author.email if ticket.author else None
    recipients = [
        email
        for email in staff_emails_for_project(db, ticket.project_id)
        if email != author_email
    ]
    lang = DEFAULT_LANG
    _broadcast(
        background,
        recipients,
        t(lang, "email.new_ticket.subject", title=ticket.title),
        "new_ticket.html",
        {"ticket": ticket, "url": url},
        lang=lang,
    )


def _load_ticket_for_notify(db: Session, ticket_id: int) -> Ticket | None:
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


def _client_circle_emails(ticket: Ticket, exclude_user_id: int | None) -> set[str]:
    emails: set[str] = set()
    if ticket.author and ticket.author.id != exclude_user_id:
        emails.add(ticket.author.email)
    for p in ticket.participants:
        if p.user_id == exclude_user_id or not p.user:
            continue
        if p.user.is_staff:
            continue
        emails.add(p.user.email)
    return emails


def notify_new_comment(
    background: BackgroundTasks,
    db: Session,
    ticket: Ticket,
    author_id: int,
    *,
    is_internal: bool = False,
) -> None:
    if is_internal:
        return
    loaded = _load_ticket_for_notify(db, ticket.id) or ticket
    url = _ticket_url(loaded)
    author = db.get(User, author_id)
    recipients: set[str] = set()
    if author and author.is_staff:
        recipients = _client_circle_emails(loaded, author_id)
    else:
        recipients = set(staff_emails_for_project(db, loaded.project_id))
        if loaded.assignee and loaded.assignee.id != author_id:
            recipients.add(loaded.assignee.email)
        if author:
            recipients.discard(author.email)
    lang = DEFAULT_LANG
    _broadcast(
        background,
        recipients,
        t(lang, "email.new_comment.subject", title=loaded.title),
        "new_comment.html",
        {"ticket": loaded, "url": url},
        lang=lang,
    )


def notify_status_change(
    background: BackgroundTasks, db: Session, ticket: Ticket, actor_id: int
) -> None:
    loaded = _load_ticket_for_notify(db, ticket.id) or ticket
    url = _ticket_url(loaded)
    recipients = _client_circle_emails(loaded, actor_id)
    recipients.update(staff_emails_for_project(db, loaded.project_id))
    actor = db.get(User, actor_id)
    if actor:
        recipients.discard(actor.email)
    lang = DEFAULT_LANG
    status_label = t(lang, f"enums.ticket_status.{loaded.status.value}")
    _broadcast(
        background,
        recipients,
        t(lang, "email.status_change.subject", title=loaded.title),
        "status_change.html",
        {"ticket": loaded, "url": url, "status_label": status_label},
        lang=lang,
    )


def notify_assignment(
    background: BackgroundTasks, ticket: Ticket, assignee: User
) -> None:
    url = _ticket_url(ticket)
    lang = DEFAULT_LANG
    queue_email(
        background,
        assignee.email,
        t(lang, "email.assignment.subject", title=ticket.title),
        "assignment.html",
        {"ticket": ticket, "url": url, "assignee": assignee},
        lang=lang,
    )
