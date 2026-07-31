from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select, update

from app.config import get_settings
from app.db.session import SessionLocal
from app.logging_setup import setup_logging
from app.models.email_outbox import EmailOutbox
from app.models.enums import EmailOutboxPriority, EmailOutboxStatus
from app.services.email import send_email_sync

logger = logging.getLogger("pulsedeck.mail")


def _recover_stuck(db) -> None:
    db.execute(
        update(EmailOutbox)
        .where(EmailOutbox.status == EmailOutboxStatus.SENDING)
        .values(status=EmailOutboxStatus.PENDING)
    )
    db.commit()


def _ticket_rate_ok(db, settings) -> bool:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    sent = db.scalar(
        select(func.count())
        .select_from(EmailOutbox)
        .where(
            EmailOutbox.priority == EmailOutboxPriority.TICKET,
            EmailOutbox.status == EmailOutboxStatus.SENT,
            EmailOutbox.sent_at >= since,
        )
    )
    if (sent or 0) >= settings.mail_max_per_hour:
        return False
    last = db.scalar(
        select(EmailOutbox.sent_at)
        .where(
            EmailOutbox.priority == EmailOutboxPriority.TICKET,
            EmailOutbox.status == EmailOutboxStatus.SENT,
            EmailOutbox.sent_at.is_not(None),
        )
        .order_by(EmailOutbox.sent_at.desc())
        .limit(1)
    )
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (
        datetime.now(timezone.utc) - last
    ).total_seconds() * 1000 >= settings.mail_min_interval_ms


def claim_next(db) -> EmailOutbox | None:
    now = datetime.now(timezone.utc)
    settings = get_settings()
    row = db.scalar(
        select(EmailOutbox)
        .where(
            EmailOutbox.status == EmailOutboxStatus.PENDING,
            EmailOutbox.available_at <= now,
        )
        .order_by(
            case((EmailOutbox.priority == EmailOutboxPriority.AUTH, 0), else_=1),
            EmailOutbox.id.asc(),
        )
        .with_for_update(skip_locked=True)
    )
    if row is None:
        db.rollback()
        return None
    if row.priority == EmailOutboxPriority.TICKET and not _ticket_rate_ok(db, settings):
        db.rollback()
        return None
    row.status = EmailOutboxStatus.SENDING
    db.commit()
    db.refresh(row)
    return row


def process_row(db, row: EmailOutbox) -> None:
    settings = get_settings()
    ok = send_email_sync(row.to_email, row.subject, row.html_body)
    row.attempts += 1
    if ok:
        row.status = EmailOutboxStatus.SENT
        row.sent_at = datetime.now(timezone.utc)
        row.last_error = None
    elif row.attempts >= settings.mail_max_attempts:
        row.status = EmailOutboxStatus.FAILED
        row.last_error = "send failed"
        logger.error(
            "Email outbox id=%s failed permanently to=%s", row.id, row.to_email
        )
    else:
        row.status = EmailOutboxStatus.PENDING
        row.available_at = datetime.now(timezone.utc) + timedelta(
            seconds=min(300, 2**row.attempts)
        )
        row.last_error = "send failed"
    db.commit()


def run_forever() -> None:
    settings = get_settings()
    logger.info(
        "Mail worker started idle_ms=%s min_interval_ms=%s max_per_hour=%s",
        settings.mail_idle_ms,
        settings.mail_min_interval_ms,
        settings.mail_max_per_hour,
    )
    with SessionLocal() as db:
        _recover_stuck(db)
    while True:
        try:
            with SessionLocal() as db:
                row = claim_next(db)
                if row is None:
                    time.sleep(max(0.05, settings.mail_idle_ms / 1000))
                    continue
                process_row(db, row)
        except Exception:
            logger.exception("Mail worker loop error")
            time.sleep(max(1.0, settings.mail_idle_ms / 1000))


def main() -> None:
    setup_logging()
    run_forever()


if __name__ == "__main__":
    main()
