from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.load_env import apply_env_file

DEFAULT_ENV = ROOT / "deploy" / ".env.dev"
DEFAULT_MAILPIT_HOST = "192.168.50.50"
DEFAULT_MAILPIT_PORT = 1025
LANG = "pl"
APP = "PulseDeck"


def main() -> int:
    parser = argparse.ArgumentParser(description="Test SMTP / Mailpit — PulseDeck")
    parser.add_argument(
        "to",
        nargs="?",
        default="test@pulsedeck.local",
        help="Adres odbiorcy (domyślnie test@pulsedeck.local)",
    )
    parser.add_argument(
        "--env",
        default=str(DEFAULT_ENV),
        help="Ścieżka do pliku .env (domyślnie deploy/.env.dev)",
    )
    parser.add_argument(
        "--mailpit",
        action="store_true",
        help="Wymuś SMTP na Mailpit (nadpisuje SMTP_* z .env)",
    )
    parser.add_argument("--smtp-server", default="", help="Nadpisz SMTP_SERVER")
    parser.add_argument("--smtp-port", type=int, default=0, help="Nadpisz SMTP_PORT")
    args = parser.parse_args()

    env_path = Path(args.env)
    if env_path.is_file():
        apply_env_file(env_path, override=True)
    elif args.env != str(DEFAULT_ENV):
        print(f"Brak pliku: {env_path}", file=sys.stderr)
        return 1

    if args.mailpit:
        os.environ["SMTP_SERVER"] = args.smtp_server or DEFAULT_MAILPIT_HOST
        os.environ["SMTP_PORT"] = str(args.smtp_port or DEFAULT_MAILPIT_PORT)
        os.environ["SMTP_USE_SSL"] = "false"
        os.environ["SMTP_USER"] = ""
        os.environ["SMTP_PASS"] = ""
        os.environ.setdefault("EMAIL_FROM", "PulseDeck Test <noreply@pulsedeck.local>")
    else:
        if args.smtp_server:
            os.environ["SMTP_SERVER"] = args.smtp_server
        if args.smtp_port:
            os.environ["SMTP_PORT"] = str(args.smtp_port)

    os.environ.setdefault("DATABASE_URL", "sqlite://")
    os.environ.setdefault("STORAGE_SECRET", "mailpit-test-secret")

    from app.config import get_settings
    from app.services.email import render_email_html, send_email_sync
    from app.utils.i18n import t
    from app.utils.unsubscribe import make_unsubscribe_url

    get_settings.cache_clear()
    settings = get_settings()
    if not settings.smtp_configured:
        print(
            "SMTP nie skonfigurowane — ustaw SMTP_SERVER lub użyj --mailpit.",
            file=sys.stderr,
        )
        return 1

    recipient = args.to.strip()
    user = SimpleNamespace(
        id=1,
        email=recipient,
        first_name="Jan",
        last_name="Kowalski",
    )
    ticket = SimpleNamespace(title="Testowe zgłoszenie Mailpit")
    ticket_url = f"{settings.app_base_url}/t/DEMO-1"
    activate_url = f"{settings.app_base_url}/auth/activate?token=mailpit-test-token"
    confirm_url = f"{settings.app_base_url}/auth/confirm-email?token=mailpit-test-token"

    def notify_ctx(pref: str, **extra):
        url = make_unsubscribe_url(1, pref)
        return {
            "user": user,
            "ticket": ticket,
            "url": ticket_url,
            "label": "DEMO-1",
            "unsubscribe_url": url,
            **extra,
        }, url

    new_ticket_ctx, new_ticket_unsub = notify_ctx("notify_new_ticket")
    comment_ctx, comment_unsub = notify_ctx("notify_reply")
    update_ctx, update_unsub = notify_ctx(
        "notify_ticket_update", change_key="enums.ticket_status.IN_PROGRESS"
    )

    samples = [
        (
            t(LANG, "email.confirm.subject", app=APP),
            "email_confirm.html",
            {
                "user": user,
                "url": confirm_url,
                "ttl_minutes": settings.email_confirm_ttl_minutes,
            },
            None,
        ),
        (
            t(LANG, "email.activate.subject", app=APP),
            "account_activate.html",
            {
                "user": user,
                "url": activate_url,
                "ttl_days": settings.auth_link_ttl_days,
            },
            None,
        ),
        (
            t(LANG, "email.reset.subject", app=APP),
            "password_reset.html",
            {
                "user": user,
                "url": activate_url,
                "ttl_days": settings.auth_link_ttl_days,
            },
            None,
        ),
        (
            t(LANG, "email.new_ticket.subject", label="DEMO-1", title=ticket.title),
            "new_ticket.html",
            new_ticket_ctx,
            new_ticket_unsub,
        ),
        (
            t(LANG, "email.new_comment.subject", label="DEMO-1", title=ticket.title),
            "new_comment.html",
            comment_ctx,
            comment_unsub,
        ),
        (
            t(LANG, "email.ticket_update.subject", label="DEMO-1", title=ticket.title),
            "ticket_update.html",
            update_ctx,
            update_unsub,
        ),
        (
            t(LANG, "email.assignment.subject", label="DEMO-1", title=ticket.title),
            "assignment.html",
            {
                "ticket": ticket,
                "url": ticket_url,
                "label": "DEMO-1",
                "user": user,
            },
            None,
        ),
        (
            t(LANG, "email.unassignment.subject", label="DEMO-1", title=ticket.title),
            "unassignment.html",
            {
                "ticket": ticket,
                "url": ticket_url,
                "label": "DEMO-1",
                "user": user,
            },
            None,
        ),
    ]

    print(
        f"[SMTP] {settings.smtp_server}:{settings.smtp_port} ssl={settings.smtp_use_ssl}"
    )
    print(f"[LANG] {LANG} — {len(samples)} wiadomości → {recipient}")
    failed = 0
    for subject, template, context, list_unsub in samples:
        html = render_email_html(template, context, lang=LANG)
        print(f"[SEND] {subject}")
        if not send_email_sync(
            recipient, subject, html, list_unsubscribe_url=list_unsub
        ):
            print(f"  BLAD — {template}", file=sys.stderr)
            failed += 1
        else:
            print(f"  OK — {template}")

    if failed:
        print(f"BLAD — nieudanych: {failed}/{len(samples)}", file=sys.stderr)
        return 1
    print(f"OK — wysłano {len(samples)} wiadomości (sprawdź UI Mailpit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
