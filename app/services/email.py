from __future__ import annotations

import logging
import re
import smtplib
import socket
from collections.abc import Iterable
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from functools import cache, partial
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings, project_root
from app.models.email_outbox import EmailOutbox
from app.models.enums import EmailOutboxPriority, EmailOutboxStatus
from app.models.ticket import Ticket, TicketParticipant
from app.models.user import User
from app.services import projects as project_service
from app.services import reply_token as reply_token_service
from app.services.auth import login_blocked_reason
from app.services.portal_settings import PortalSettings, get_portal_settings
from app.services.tickets import is_ticket_involved, is_ticket_watcher
from app.utils.i18n import DEFAULT_LANG, normalize_lang, t
from app.utils.unsubscribe import make_unsubscribe_url
from app.utils.unwatch import make_unwatch_url
from app.utils.urls import ticket_label, ticket_path

logger = logging.getLogger("pulsedeck.mail")

APP_NAME = "PulseDeck"
LOGO_CID = "pulsedeck-logo-mail"
LOGO_PATH = (
    project_root() / "frontend" / "static" / "images" / "pulsedeck-logo-mail.png"
)

_env = Environment(
    loader=FileSystemLoader(str(project_root() / "app" / "templates" / "email")),
    autoescape=select_autoescape(["html", "xml"]),
)

_BLOCK_TAGS = frozenset(
    {"p", "div", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "hr"}
)
_SKIP_TAGS = frozenset({"script", "style", "head", "title"})


class _HTMLToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._chunks: list[str] = []
        self._skip = 0
        self._href: str | None = None
        self._link_start = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "br" or tag == "hr":
            self._chunks.append("\n")
            return
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_start = len(self._chunks)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag == "a" and self._href:
            href = self._href.strip()
            label = "".join(self._chunks[self._link_start :]).strip()
            self._href = None
            if href and not href.startswith("cid:") and href != label:
                self._chunks.append(f" ({href})")
        if tag in _BLOCK_TAGS and tag not in {"br", "hr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and data:
            self._chunks.append(data)

    def text(self) -> str:
        raw = unescape("".join(self._chunks))
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip()


def html_to_plain(html_body: str) -> str:
    parser = _HTMLToText()
    try:
        parser.feed(html_body)
        parser.close()
    except Exception:
        logger.exception("Failed to convert HTML email to plain text")
        return re.sub(r"<[^>]+>", " ", html_body)
    return parser.text()


def _mail_domain(from_addr: str, app_base_url: str) -> str:
    _, addr = parseaddr(from_addr)
    if "@" in addr:
        return addr.rsplit("@", 1)[-1].strip().lower()
    host = urlparse(app_base_url).hostname
    return (host or "localhost").lower()


@cache
def _smtp_local_hostname() -> str:
    fqdn = socket.getfqdn().strip()
    if "." in fqdn:
        return fqdn
    addr = "127.0.0.1"
    try:
        addr = socket.gethostbyname(socket.gethostname())
    except OSError:
        pass
    return f"[{addr}]"


def _smtp_connect(portal: PortalSettings) -> smtplib.SMTP:
    host = portal.smtp_server
    port = portal.smtp_port
    local_hostname = _smtp_local_hostname()
    if portal.smtp_security == "ssl":
        return smtplib.SMTP_SSL(host, port, local_hostname=local_hostname, timeout=30)
    smtp = smtplib.SMTP(host, port, local_hostname=local_hostname, timeout=30)
    smtp.ehlo()
    if portal.smtp_security == "starttls":
        if not smtp.has_extn("starttls"):
            raise RuntimeError("SMTP server does not support STARTTLS")
        smtp.starttls()
        smtp.ehlo()
    return smtp


def _build_message(
    to: str,
    subject: str,
    html_body: str,
    *,
    list_unsubscribe_url: str | None = None,
    portal: PortalSettings | None = None,
) -> EmailMessage:
    settings = get_settings()
    portal = portal or get_portal_settings()
    from_addr = portal.email_from_address
    domain = _mail_domain(from_addr, settings.app_base_url)
    plain = html_to_plain(html_body)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["MIME-Version"] = "1.0"
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    msg["X-Mailer"] = APP_NAME
    msg["List-Id"] = f"<{APP_NAME.lower()}.{domain}>"
    if list_unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{list_unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    msg.set_content(plain, charset="utf-8")
    msg.add_alternative(html_body, subtype="html", charset="utf-8")
    html_part = msg.get_body(preferencelist=("html",))
    if html_part is not None and LOGO_PATH.is_file():
        html_part.add_related(
            LOGO_PATH.read_bytes(),
            maintype="image",
            subtype="png",
            cid=LOGO_CID,
        )
    elif not LOGO_PATH.is_file():
        logger.warning("Email logo missing: %s", LOGO_PATH)
    return msg


def send_email_sync(
    to: str,
    subject: str,
    html_body: str,
    *,
    list_unsubscribe_url: str | None = None,
    db: Session | None = None,
) -> bool:
    portal = get_portal_settings(db)
    if not portal.smtp_configured:
        logger.warning("SMTP not configured — skip email to %s subject=%s", to, subject)
        return False
    msg = _build_message(
        to,
        subject,
        html_body,
        list_unsubscribe_url=list_unsubscribe_url,
        portal=portal,
    )
    try:
        with _smtp_connect(portal) as smtp:
            _smtp_auth(smtp, portal.smtp_user, portal.smtp_pass)
            smtp.send_message(msg)
        logger.info("Email sent to %s subject=%s", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


def _smtp_auth(smtp: smtplib.SMTP, user: str, password: str) -> None:
    if user.strip() and password:
        smtp.login(user, password)


def ticket_email_body(
    lang: str, mail_key: str, label: str, title: str | None, **kwargs
) -> Markup:
    ref = Markup(
        '<strong style="font-weight:600;color:#0f172a">'
        f"{escape(label)}: {escape(title or '')}</strong>"
    )
    return Markup(t(lang, f"email.{mail_key}.body", ticket=ref, app=APP_NAME, **kwargs))


def render_email_html(template: str, context: dict, *, lang: str = DEFAULT_LANG) -> str:
    return _env.get_template(template).render(
        **context,
        app_name=APP_NAME,
        ui_lang=lang,
        logo_src=f"cid:{LOGO_CID}",
        t=partial(t, lang),
        ticket_email_body=partial(ticket_email_body, lang),
    )


def send_smtp_test(*, to_email: str, lang: str, db: Session | None = None) -> bool:
    subject = t(lang, "email.smtp_test.subject")
    html = render_email_html("smtp_test.html", {}, lang=lang)
    return send_email_sync(to_email, subject, html, db=db)


def enqueue_email(
    db: Session,
    *,
    to_email: str,
    subject: str,
    html_body: str,
    priority: EmailOutboxPriority = EmailOutboxPriority.TICKET,
    list_unsubscribe_url: str | None = None,
) -> None:
    db.add(
        EmailOutbox(
            priority=priority,
            to_email=to_email.strip().lower(),
            subject=subject,
            html_body=html_body,
            list_unsubscribe_url=list_unsubscribe_url,
            status=EmailOutboxStatus.PENDING,
            available_at=datetime.now(timezone.utc),
        )
    )


def _enqueue_users(
    db: Session,
    recipients: Iterable[User],
    subject_key: str,
    template: str,
    context: dict,
    *,
    pref: str,
) -> None:
    seen: set[str] = set()
    for user in recipients:
        email = (user.email or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        lang = normalize_lang(user.ui_lang)
        unsub = make_unsubscribe_url(user.id, pref)
        html = render_email_html(
            template,
            {**context, "user": user, "unsubscribe_url": unsub},
            lang=lang,
        )
        enqueue_email(
            db,
            to_email=email,
            subject=t(lang, subject_key),
            html_body=html,
            list_unsubscribe_url=unsub,
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


def project_staff(db: Session, ticket: Ticket) -> set[User]:
    return set(project_service.list_project_staff(db, ticket.project_id))


def _involved_users(ticket: Ticket) -> dict[int, User]:
    by_id: dict[int, User] = {}
    for user in (
        ticket.author,
        ticket.assignee,
        *(participant.user for participant in ticket.participants or []),
    ):
        if user and user.is_active:
            by_id[user.id] = user
    return by_id


def _involved_staff(db: Session, ticket: Ticket) -> set[User]:
    return {
        user
        for user in _involved_users(ticket).values()
        if project_service.is_project_staff(db, ticket.project_id, user)
    }


def _staff_recipients(db: Session, ticket: Ticket) -> set[User]:
    staff = _involved_staff(db, ticket)
    return staff or project_staff(db, ticket)


def _client_recipients(db: Session, ticket: Ticket) -> set[User]:
    return {
        user
        for user_id, user in _involved_users(ticket).items()
        if user_id == ticket.author_id
        or not project_service.is_project_staff(db, ticket.project_id, user)
    }


def comment_recipients(
    db: Session,
    ticket: Ticket,
    *,
    internal: bool,
) -> set[User]:
    staff_targets = (
        {ticket.assignee}
        if ticket.assignee is not None and ticket.assignee.is_active
        else project_staff(db, ticket)
    )
    if internal:
        watchers = {
            p.user
            for p in (ticket.participants or [])
            if p.user
            and p.user.is_active
            and project_service.is_project_staff(db, ticket.project_id, p.user)
        }
        return watchers | staff_targets
    return set(_involved_users(ticket).values()) | staff_targets


def _pipeline_recipients(
    users: Iterable[User],
    *,
    actor_id: int | None,
    pref: str | None,
    ticket: Ticket | None = None,
) -> list[User]:
    by_email: dict[str, User] = {}
    for user in users:
        if not user.is_active:
            continue
        if (
            ticket is not None
            and user.is_admin
            and not is_ticket_involved(user, ticket)
        ):
            continue
        if actor_id is not None and user.id == actor_id:
            continue
        if pref is not None and not getattr(user, pref, False):
            continue
        email = (user.email or "").strip().lower()
        if not email or email in by_email:
            continue
        by_email[email] = user
    return list(by_email.values())


def _ticket_mail_ctx(ticket: Ticket, **extra) -> dict:
    settings = get_settings()
    try:
        label = ticket_label(ticket)
        url = f"{settings.app_base_url}{ticket_path(ticket)}"
    except ValueError:
        label = str(ticket.number)
        url = f"{settings.app_base_url}/"
    return {
        "ticket": ticket,
        "url": url,
        "label": label,
        "project_name": getattr(getattr(ticket, "project", None), "name", None),
        **extra,
    }


def _send_pref_mails(
    db: Session,
    recipients: list[User],
    *,
    key: str,
    pref: str,
    ctx: dict,
) -> None:
    if not recipients:
        return
    _enqueue_users(
        db,
        recipients,
        f"email.{key}.subject",
        f"{key}.html",
        ctx,
        pref=pref,
    )


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


def _emit_group(
    db: Session,
    ticket: Ticket,
    *,
    actor_id: int | None,
    group: set[User],
    mail_key: str,
    pref: str | None,
    ctx: dict | None = None,
) -> None:
    recipients = _pipeline_recipients(
        group, actor_id=actor_id, pref=pref, ticket=ticket
    )
    if not recipients:
        return
    if pref is None:
        loaded_ctx = ctx or _ticket_mail_ctx(ticket)
        for user in recipients:
            lang = normalize_lang(user.ui_lang)
            enqueue_email(
                db,
                to_email=user.email,
                subject=t(lang, f"email.{mail_key}.subject"),
                html_body=render_email_html(
                    f"{mail_key}.html",
                    {**loaded_ctx, "user": user},
                    lang=lang,
                ),
            )
        db.commit()
        return
    _send_pref_mails(
        db,
        recipients,
        key=mail_key,
        pref=pref,
        ctx=ctx or _ticket_mail_ctx(ticket),
    )


def emit_ticket_created(db: Session, ticket: Ticket, *, actor_id: int) -> None:
    loaded = _load_ticket(db, ticket.id) or ticket
    group = project_staff(db, loaded)
    author = loaded.author
    project = loaded.project
    if (
        project
        and project.notify_clients_on_staff_ticket
        and author
        and project_service.user_has_staff_ops(author)
    ):
        group |= set(project_service.list_project_clients(db, project.id))
    _emit_group(
        db,
        loaded,
        actor_id=actor_id,
        group=group,
        mail_key="new_ticket",
        pref="notify_new_ticket",
    )


def emit_comment(
    db: Session,
    ticket: Ticket,
    author_id: int,
    *,
    is_internal: bool = False,
) -> None:
    loaded = _load_ticket(db, ticket.id) or ticket
    recipients = _pipeline_recipients(
        comment_recipients(db, loaded, internal=is_internal),
        actor_id=author_id,
        pref="notify_reply",
        ticket=loaded,
    )
    if not recipients:
        return
    base_ctx = _ticket_mail_ctx(loaded)
    base = get_settings().app_base_url.rstrip("/")
    for user in recipients:
        lang = normalize_lang(user.ui_lang)
        unsub = make_unsubscribe_url(user.id, "notify_reply")
        unwatch = (
            make_unwatch_url(user.id, loaded.id)
            if is_ticket_watcher(loaded, user.id)
            else None
        )
        if login_blocked_reason(user) is None:
            raw = reply_token_service.create_reply_token(db, user, loaded)
            reply_url = f"{base}/open/{raw}"
        else:
            reply_url = None
        enqueue_email(
            db,
            to_email=user.email,
            subject=t(lang, "email.new_comment.subject"),
            html_body=render_email_html(
                "new_comment.html",
                {
                    **base_ctx,
                    "url": reply_url or base_ctx["url"],
                    "reply_url": reply_url,
                    "login_url": f"{base}/login",
                    "user": user,
                    "unsubscribe_url": unsub,
                    "unwatch_url": unwatch,
                },
                lang=lang,
            ),
            list_unsubscribe_url=unsub,
        )
    db.commit()


def emit_ticket_assigned(
    db: Session,
    ticket: Ticket,
    *,
    actor_id: int,
    previous: User | None,
    new: User | None,
) -> None:
    if new is None or new.id == actor_id:
        return
    if previous is not None and previous.id == new.id:
        return
    loaded = _load_ticket(db, ticket.id) or ticket
    recipients = _pipeline_recipients(
        [new], actor_id=actor_id, pref=None, ticket=loaded
    )
    if not recipients:
        return
    ctx = _ticket_mail_ctx(loaded)
    for user in recipients:
        lang = normalize_lang(user.ui_lang)
        enqueue_email(
            db,
            to_email=user.email,
            subject=t(lang, "email.assignment.subject"),
            html_body=render_email_html(
                "assignment.html", {**ctx, "user": user}, lang=lang
            ),
        )
    db.commit()


def emit_ticket_updated(
    db: Session, ticket: Ticket, actor_id: int, *, change_key: str
) -> None:
    loaded = _load_ticket(db, ticket.id) or ticket
    _emit_group(
        db,
        loaded,
        actor_id=actor_id,
        group=_client_recipients(db, loaded),
        mail_key="ticket_update",
        pref="notify_ticket_update",
        ctx=_ticket_mail_ctx(loaded, change_key=change_key),
    )


def emit_ticket_closed(
    db: Session, ticket: Ticket, actor_id: int, *, change_key: str
) -> None:
    emit_ticket_updated(db, ticket, actor_id, change_key=change_key)


def emit_ticket_reopened(
    db: Session, ticket: Ticket, actor_id: int, *, change_key: str
) -> None:
    loaded = _load_ticket(db, ticket.id) or ticket
    _emit_group(
        db,
        loaded,
        actor_id=actor_id,
        group=_staff_recipients(db, loaded),
        mail_key="ticket_update",
        pref="notify_ticket_update",
        ctx=_ticket_mail_ctx(loaded, change_key=change_key),
    )


def notify_email_confirm(
    db: Session,
    user: User,
    token: str,
    to_email: str,
) -> None:
    lang = normalize_lang(user.ui_lang)
    settings = get_settings()
    portal = get_portal_settings(db)
    _enqueue_auth(
        db,
        to_email=to_email,
        subject=t(lang, "email.confirm.subject"),
        template="email_confirm.html",
        context={
            "user": user,
            "url": f"{settings.app_base_url}/auth/confirm-email?token={token}",
            "ttl_minutes": portal.email_confirm_ttl_minutes,
        },
        lang=lang,
    )


def notify_password_set(
    db: Session,
    user: User,
    token: str,
) -> None:
    lang = normalize_lang(user.ui_lang)
    settings = get_settings()
    portal = get_portal_settings(db)
    activation = user.activated_at is None
    _enqueue_auth(
        db,
        to_email=user.email,
        subject=t(
            lang,
            "email.activate.subject" if activation else "email.reset.subject",
        ),
        template="account_activate.html" if activation else "password_reset.html",
        context={
            "user": user,
            "url": f"{settings.app_base_url}/auth/activate?token={token}",
            "ttl_days": portal.auth_link_ttl_days,
        },
        lang=lang,
    )


def notify_new_ticket(db: Session, ticket: Ticket) -> None:
    emit_ticket_created(db, ticket, actor_id=ticket.author_id)


def notify_new_comment(
    db: Session,
    ticket: Ticket,
    author_id: int,
    *,
    is_internal: bool = False,
) -> None:
    emit_comment(db, ticket, author_id, is_internal=is_internal)


def notify_ticket_update(
    db: Session, ticket: Ticket, actor_id: int, *, change_key: str
) -> None:
    if change_key.endswith(".DONE") or "ticket_status.DONE" in change_key:
        emit_ticket_closed(db, ticket, actor_id, change_key=change_key)
        return
    emit_ticket_updated(db, ticket, actor_id, change_key=change_key)


def notify_assignment(
    db: Session,
    ticket: Ticket,
    *,
    actor_id: int,
    previous: User | None,
    new: User | None,
) -> None:
    emit_ticket_assigned(db, ticket, actor_id=actor_id, previous=previous, new=new)
