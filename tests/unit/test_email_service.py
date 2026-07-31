from unittest.mock import MagicMock, patch

from app.models.email_outbox import EmailOutbox
from app.models.enums import EmailOutboxPriority, TicketType
from app.services import email as email_service
from app.services import tickets as ticket_service


class TestEnqueueAndRender:
    def test_enqueue_email(self, db_session):
        email_service.enqueue_email(
            db_session,
            to_email="A@Test.Local",
            subject="Hello",
            html_body="<p>Hi</p>",
            priority=EmailOutboxPriority.AUTH,
        )
        db_session.commit()
        from sqlalchemy import select

        row = db_session.scalar(select(EmailOutbox))
        assert row is not None
        assert row.to_email == "a@test.local"
        assert row.priority == EmailOutboxPriority.AUTH
        assert row.list_unsubscribe_url is None

    def test_build_message_list_unsubscribe_headers(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("EMAIL_FROM", "PulseDeck <noreply@pulsedeck.local>")
        get_settings.cache_clear()
        try:
            unsub = "https://pulsedeck.lan/email/unsubscribe?token=abc"
            msg = email_service._build_message(
                "a@b.c",
                "subj",
                "<p>hi</p>",
                list_unsubscribe_url=unsub,
            )
            assert msg["List-Unsubscribe"] == f"<{unsub}>"
            assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
            bare = email_service._build_message("a@b.c", "subj", "<p>hi</p>")
            assert bare.get("List-Unsubscribe") is None
            assert bare.get("List-Unsubscribe-Post") is None
        finally:
            get_settings.cache_clear()

    def test_render_email_html(self):
        html = email_service.render_email_html(
            "email_confirm.html",
            {
                "user": MagicMock(first_name="Ada"),
                "url": "http://test/confirm",
                "ttl_minutes": 60,
            },
        )
        assert "http://test/confirm" in html

    def test_send_email_sync_without_smtp(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("SMTP_SERVER", "")
        get_settings.cache_clear()
        try:
            assert email_service.send_email_sync("a@b.c", "x", "<p>y</p>") is False
        finally:
            get_settings.cache_clear()

    def test_send_email_sync_with_smtp_ssl(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("SMTP_SERVER", "smtp.test")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USE_SSL", "true")
        monkeypatch.setenv("SMTP_USER", "u")
        monkeypatch.setenv("SMTP_PASS", "p")
        monkeypatch.setenv("EMAIL_FROM", "from@test.local")
        get_settings.cache_clear()
        try:
            smtp = MagicMock()
            smtp.__enter__.return_value = smtp
            smtp.__exit__.return_value = False
            with patch("app.services.email.smtplib.SMTP_SSL", return_value=smtp):
                assert (
                    email_service.send_email_sync("a@b.c", "subj", "<p>body</p>")
                    is True
                )
            smtp.login.assert_called_once()
            smtp.send_message.assert_called_once()
        finally:
            get_settings.cache_clear()

    def test_send_email_sync_exception(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("SMTP_SERVER", "smtp.test")
        get_settings.cache_clear()
        try:
            with patch(
                "app.services.email.smtplib.SMTP",
                side_effect=OSError("down"),
            ):
                assert (
                    email_service.send_email_sync("a@b.c", "subj", "<p>body</p>")
                    is False
                )
        finally:
            get_settings.cache_clear()


class TestNotify:
    def test_notify_password_set_activation(self, db_session, client_user):
        client_user.activated_at = None
        db_session.commit()
        email_service.notify_password_set(db_session, client_user, "tok")
        from sqlalchemy import select

        row = db_session.scalar(select(EmailOutbox))
        assert row is not None
        assert row.priority == EmailOutboxPriority.AUTH

    def test_notify_email_confirm(self, db_session, client_user):
        email_service.notify_email_confirm(
            db_session, client_user, "tok", "new@test.local"
        )
        from sqlalchemy import select

        row = db_session.scalar(select(EmailOutbox))
        assert row is not None
        assert row.to_email == "new@test.local"

    def test_notify_new_ticket_from_client(
        self, db_session, project_with_members, client_user, staff_user
    ):
        staff_user.notify_new_ticket = True
        db_session.commit()
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Notify me",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        email_service.notify_new_ticket(db_session, ticket)
        from sqlalchemy import select

        rows = list(db_session.scalars(select(EmailOutbox)).all())
        assert len(rows) >= 1
        assert rows[0].list_unsubscribe_url
        assert "/email/unsubscribe?token=" in rows[0].list_unsubscribe_url
        assert "/email/unsubscribe?token=" in rows[0].html_body

    def test_notify_new_ticket_skips_staff_author(
        self, db_session, project_with_members, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Staff ticket",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        email_service.notify_new_ticket(db_session, ticket)
        from sqlalchemy import select

        assert db_session.scalar(select(EmailOutbox)) is None

    def test_notify_new_comment(
        self, db_session, project_with_members, client_user, staff_user
    ):
        staff_user.notify_reply = True
        db_session.commit()
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Comment notify",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        email_service.notify_new_comment(db_session, ticket, client_user.id)
        from sqlalchemy import select

        assert db_session.scalar(select(EmailOutbox)) is not None

    def test_notify_new_comment_internal_skipped(
        self, db_session, project_with_members, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Internal",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        email_service.notify_new_comment(
            db_session, ticket, staff_user.id, is_internal=True
        )
        from sqlalchemy import select

        assert db_session.scalar(select(EmailOutbox)) is None

    def test_notify_uses_recipient_ui_lang(
        self, db_session, project_with_members, client_user, staff_user
    ):
        staff_user.notify_new_ticket = True
        staff_user.ui_lang = "pl"
        db_session.commit()
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Lang",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        email_service.notify_new_ticket(db_session, ticket)
        from sqlalchemy import select

        row = db_session.scalar(
            select(EmailOutbox).where(EmailOutbox.to_email == staff_user.email)
        )
        assert row is not None
        assert 'lang="pl"' in row.html_body
        assert "Nowe zgłoszenie" in row.subject

    def test_notify_ticket_update(
        self, db_session, project_with_members, client_user, staff_user
    ):
        client_user.notify_ticket_update = True
        db_session.commit()
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Update",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        email_service.notify_ticket_update(
            db_session, ticket, staff_user.id, change_key="enums.ticket_status.DONE"
        )
        from sqlalchemy import select

        assert db_session.scalar(select(EmailOutbox)) is not None

    def test_notify_assignment(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Assign",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        email_service.notify_assignment(
            db_session,
            ticket,
            actor_id=client_user.id,
            previous=None,
            new=staff_user,
        )
        from sqlalchemy import select

        row = db_session.scalar(select(EmailOutbox))
        assert row is not None
        assert row.to_email == staff_user.email
