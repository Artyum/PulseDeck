from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.models.email_outbox import EmailOutbox
from app.models.enums import EmailOutboxPriority, EmailOutboxStatus
from app.workers import mail as mail_worker


def _row(
    db,
    *,
    priority=EmailOutboxPriority.AUTH,
    status=EmailOutboxStatus.PENDING,
    available_at=None,
    attempts=0,
    sent_at=None,
):
    row = EmailOutbox(
        priority=priority,
        to_email="user@test.local",
        subject="Hi",
        html_body="<p>x</p>",
        status=status,
        available_at=available_at or datetime.now(timezone.utc),
        attempts=attempts,
        sent_at=sent_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestRecoverStuck:
    def test_resets_sending_to_pending(self, db_session):
        stuck = _row(db_session, status=EmailOutboxStatus.SENDING)
        mail_worker._recover_stuck(db_session)
        db_session.refresh(stuck)
        assert stuck.status == EmailOutboxStatus.PENDING


class TestTicketRateOk:
    def test_true_when_no_sent(self, db_session):
        settings = get_settings()
        assert mail_worker._ticket_rate_ok(db_session, settings) is True

    def test_false_when_hourly_cap_reached(self, db_session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "mail_max_per_hour", 1)
        _row(
            db_session,
            priority=EmailOutboxPriority.TICKET,
            status=EmailOutboxStatus.SENT,
            sent_at=datetime.now(timezone.utc),
        )
        assert mail_worker._ticket_rate_ok(db_session, settings) is False

    def test_false_when_min_interval_not_elapsed(self, db_session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "mail_max_per_hour", 100)
        monkeypatch.setattr(settings, "mail_min_interval_ms", 60_000)
        _row(
            db_session,
            priority=EmailOutboxPriority.TICKET,
            status=EmailOutboxStatus.SENT,
            sent_at=datetime.now(timezone.utc),
        )
        assert mail_worker._ticket_rate_ok(db_session, settings) is False

    def test_true_when_interval_elapsed(self, db_session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "mail_max_per_hour", 100)
        monkeypatch.setattr(settings, "mail_min_interval_ms", 1000)
        _row(
            db_session,
            priority=EmailOutboxPriority.TICKET,
            status=EmailOutboxStatus.SENT,
            sent_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        )
        assert mail_worker._ticket_rate_ok(db_session, settings) is True

    def test_naive_sent_at_treated_as_utc(self, db_session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "mail_max_per_hour", 100)
        monkeypatch.setattr(settings, "mail_min_interval_ms", 1000)
        _row(
            db_session,
            priority=EmailOutboxPriority.TICKET,
            status=EmailOutboxStatus.SENT,
            sent_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(seconds=5),
        )
        assert mail_worker._ticket_rate_ok(db_session, settings) is True


class TestClaimNext:
    def test_none_when_empty(self):
        db = MagicMock()
        db.scalar.return_value = None
        assert mail_worker.claim_next(db) is None
        db.rollback.assert_called_once()

    def test_claims_auth_row(self):
        row = MagicMock(priority=EmailOutboxPriority.AUTH)
        db = MagicMock()
        db.scalar.return_value = row
        claimed = mail_worker.claim_next(db)
        assert claimed is row
        assert row.status == EmailOutboxStatus.SENDING
        db.commit.assert_called()
        db.refresh.assert_called_with(row)

    def test_ticket_skipped_when_rate_limited(self, monkeypatch):
        row = MagicMock(priority=EmailOutboxPriority.TICKET)
        db = MagicMock()
        db.scalar.return_value = row
        monkeypatch.setattr(mail_worker, "_ticket_rate_ok", lambda *_a, **_k: False)
        assert mail_worker.claim_next(db) is None
        db.rollback.assert_called()


class TestProcessRow:
    def test_marks_sent_on_success(self, db_session):
        row = _row(db_session, status=EmailOutboxStatus.SENDING)
        with patch("app.workers.mail.send_email_sync", return_value=True):
            mail_worker.process_row(db_session, row)
        db_session.refresh(row)
        assert row.status == EmailOutboxStatus.SENT
        assert row.sent_at is not None
        assert row.attempts == 1

    def test_retries_on_failure(self, db_session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "mail_max_attempts", 5)
        row = _row(db_session, status=EmailOutboxStatus.SENDING, attempts=0)
        with patch("app.workers.mail.send_email_sync", return_value=False):
            mail_worker.process_row(db_session, row)
        db_session.refresh(row)
        assert row.status == EmailOutboxStatus.PENDING
        assert row.last_error == "send failed"
        assert row.attempts == 1

    def test_fails_permanently_after_max_attempts(self, db_session, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "mail_max_attempts", 2)
        row = _row(db_session, status=EmailOutboxStatus.SENDING, attempts=1)
        with patch("app.workers.mail.send_email_sync", return_value=False):
            mail_worker.process_row(db_session, row)
        db_session.refresh(row)
        assert row.status == EmailOutboxStatus.FAILED


class TestRunForever:
    def test_idle_then_error_path(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "mail_idle_ms", 1)

        db = MagicMock()
        session_cm = MagicMock()
        session_cm.__enter__.return_value = db
        session_cm.__exit__.return_value = False
        monkeypatch.setattr(mail_worker, "SessionLocal", lambda: session_cm)
        monkeypatch.setattr(mail_worker, "_recover_stuck", lambda _db: None)

        calls = {"n": 0}

        def claim(_db):
            calls["n"] += 1
            if calls["n"] == 1:
                return
            raise RuntimeError("boom")

        sleeps: list[float] = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 2:
                raise KeyboardInterrupt()

        monkeypatch.setattr(mail_worker, "claim_next", claim)
        monkeypatch.setattr(mail_worker.time, "sleep", fake_sleep)
        with pytest.raises(KeyboardInterrupt):
            mail_worker.run_forever()
        assert len(sleeps) >= 2
