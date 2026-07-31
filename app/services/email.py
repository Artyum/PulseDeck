from __future__ import annotations

import logging
import re
import smtplib
from collections.abc import Iterable
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from functools import partial
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

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
from app.utils.unsubscribe import make_unsubscribe_url
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


def _build_message(
    to: str,
    subject: str,
    html_body: str,
    *,
    list_unsubscribe_url: str | None = None,
) -> EmailMessage:
    settings = get_settings()
    from_addr = settings.email_from_address
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
) -> bool:
    settings = get_settings()
    if not settings.smtp_configured:
        logger.warning("SMTP not configured — skip email to %s subject=%s", to, subject)
        return False
    msg = _build_message(
        to, subject, html_body, list_unsubscribe_url=list_unsubscribe_url
    )
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
        logo_src=f"cid:{LOGO_CID}",
        t=partial(t, lang),
    )


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
    subject: str,
    template: str,
    context: dict,
    *,
    pref: str,
    lang: str = DEFAULT_LANG,
) -> None:
    seen: set[str] = set()
    for user in recipients:
        email = (user.email or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        unsub = make_unsubscribe_url(user.id, pref)
        html = render_email_html(
            template,
            {**context, "user": user, "unsubscribe_url": unsub},
            lang=lang,
        )
        enqueue_email(
            db,
            to_email=email,
            subject=subject,
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


def _ticket_mail_ctx(ticket: Ticket, **extra) -> dict:
    settings = get_settings()
    try:
        label = ticket_label(ticket)
        url = f"{settings.app_base_url}{ticket_path(ticket)}"
    except ValueError:
        label = str(ticket.number)
        url = f"{settings.app_base_url}/"
    return {"ticket": ticket, "url": url, "label": label, **extra}


def _send_pref_mails(
    db: Session,
    recipients: list[User],
    *,
    key: str,
    pref: str,
    ctx: dict,
    lang: str = DEFAULT_LANG,
) -> None:
    if not recipients:
        return
    ticket = ctx["ticket"]
    _enqueue_users(
        db,
        recipients,
        t(lang, f"email.{key}.subject", label=ctx["label"], title=ticket.title),
        f"{key}.html",
        ctx,
        pref=pref,
        lang=lang,
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
    _send_pref_mails(
        db,
        _pick(
            _staff_circle(db, loaded),
            exclude_id=loaded.author_id,
            pref="notify_new_ticket",
        ),
        key="new_ticket",
        pref="notify_new_ticket",
        ctx=_ticket_mail_ctx(loaded),
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
    _send_pref_mails(
        db,
        _pick(circle, exclude_id=author_id, pref="notify_reply"),
        key="new_comment",
        pref="notify_reply",
        ctx=_ticket_mail_ctx(loaded),
    )


def notify_ticket_update(
    db: Session, ticket: Ticket, actor_id: int, *, change_label: str
) -> None:
    loaded = _load_ticket(db, ticket.id) or ticket
    by_id = {u.id: u for u in (*_staff_circle(db, loaded), *_client_circle(loaded))}
    _send_pref_mails(
        db,
        _pick(by_id.values(), exclude_id=actor_id, pref="notify_ticket_update"),
        key="ticket_update",
        pref="notify_ticket_update",
        ctx=_ticket_mail_ctx(loaded, change_label=change_label),
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
    loaded = _load_ticket(db, ticket.id) or ticket
    ctx = _ticket_mail_ctx(loaded)
    for user, key in targets:
        enqueue_email(
            db,
            to_email=user.email,
            subject=t(
                lang,
                f"email.{key}.subject",
                label=ctx["label"],
                title=loaded.title,
            ),
            html_body=render_email_html(
                f"{key}.html", {**ctx, "user": user}, lang=lang
            ),
        )
    db.commit()
