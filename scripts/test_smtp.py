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
        email=recipient,
        first_name="Test",
        last_name="Mailpit",
    )
    url = f"{settings.app_base_url}/auth/activate?token=mailpit-test-token"
    html = render_email_html(
        "account_activate.html",
        {
            "user": user,
            "url": url,
            "ttl_days": settings.auth_link_ttl_days,
        },
    )
    subject = "PulseDeck — test Mailpit (aktywacja)"

    print(
        f"[SMTP] {settings.smtp_server}:{settings.smtp_port} ssl={settings.smtp_use_ssl}"
    )
    print(f"[SEND] {subject} → {recipient}")
    if not send_email_sync(recipient, subject, html):
        print("BLAD — wysylka nieudana (szczegoly w logu).", file=sys.stderr)
        return 1
    print("OK — wiadomość wysłana (sprawdź UI Mailpit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
