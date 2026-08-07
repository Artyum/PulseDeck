from unittest.mock import MagicMock, patch

from sqlalchemy import select

from app.models.email_outbox import EmailOutbox
from app.models.enums import EmailOutboxPriority, UserRole
from app.services import email as email_service
from app.services import projects as project_service
from app.services import tickets as ticket_service
from tests.helpers import make_ticket, make_user, peer_participant_ticket


def _outbox_emails(db):
    return {row.to_email for row in db.scalars(select(EmailOutbox)).all()}


def _staff_peer(db, project, email: str, *, first: str = "Other", last: str = "Staff"):
    user = make_user(
        db,
        email,
        first_name=first,
        last_name=last,
        role=UserRole.STAFF,
        project=project,
    )
    user.notify_reply = True
    db.commit()
    return user


class TestSmtpLocalHostname:
    def test_caches_fqdn(self, monkeypatch):
        email_service._smtp_local_hostname.cache_clear()
        calls = {"n": 0}

        def fake_getfqdn():
            calls["n"] += 1
            return "mail.example.com"

        monkeypatch.setattr(email_service.socket, "getfqdn", fake_getfqdn)
        assert email_service._smtp_local_hostname() == "mail.example.com"
        assert email_service._smtp_local_hostname() == "mail.example.com"
        assert calls["n"] == 1

    def test_address_literal_when_no_dot(self, monkeypatch):
        email_service._smtp_local_hostname.cache_clear()
        monkeypatch.setattr(email_service.socket, "getfqdn", lambda: "NITRO")
        monkeypatch.setattr(email_service.socket, "gethostname", lambda: "NITRO")
        monkeypatch.setattr(
            email_service.socket, "gethostbyname", lambda _h: "192.168.1.10"
        )
        assert email_service._smtp_local_hostname() == "[192.168.1.10]"


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

    def test_build_message_list_unsubscribe_headers(self, db_session, monkeypatch):
        from dataclasses import replace

        from app.services.portal_settings import get_portal_settings

        portal = replace(
            get_portal_settings(db_session),
            email_from="PulseDeck <noreply@pulsedeck.local>",
        )
        monkeypatch.setattr(
            email_service, "get_portal_settings", lambda _db=None: portal
        )
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

    def test_send_email_sync_without_smtp(self, db_session, monkeypatch):
        from dataclasses import replace

        from app.services.portal_settings import get_portal_settings

        portal = replace(get_portal_settings(db_session), smtp_server="")
        monkeypatch.setattr(
            email_service, "get_portal_settings", lambda _db=None: portal
        )
        assert email_service.send_email_sync("a@b.c", "x", "<p>y</p>") is False

    def test_send_email_sync_with_smtp_ssl(self, db_session, monkeypatch):
        from dataclasses import replace

        from app.services.portal_settings import get_portal_settings

        portal = replace(
            get_portal_settings(db_session),
            smtp_server="smtp.test",
            smtp_port=465,
            smtp_security="ssl",
            smtp_user="u",
            smtp_pass="p",
            email_from="from@test.local",
        )
        monkeypatch.setattr(
            email_service, "get_portal_settings", lambda _db=None: portal
        )
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.__exit__.return_value = False
        email_service._smtp_local_hostname.cache_clear()
        monkeypatch.setattr(
            email_service, "_smtp_local_hostname", lambda: "client.example.com"
        )
        with patch("app.services.email.smtplib.SMTP_SSL", return_value=smtp) as ctor:
            assert email_service.send_email_sync("a@b.c", "subj", "<p>body</p>") is True
        ctor.assert_called_once()
        assert ctor.call_args.kwargs.get("local_hostname") == "client.example.com"
        smtp.login.assert_called_once()
        smtp.send_message.assert_called_once()

    def test_send_email_sync_exception(self, db_session, monkeypatch):
        from dataclasses import replace

        from app.services.portal_settings import get_portal_settings

        portal = replace(
            get_portal_settings(db_session),
            smtp_server="smtp.test",
            smtp_security="none",
        )
        monkeypatch.setattr(
            email_service, "get_portal_settings", lambda _db=None: portal
        )
        with patch(
            "app.services.email.smtplib.SMTP",
            side_effect=OSError("down"),
        ):
            assert (
                email_service.send_email_sync("a@b.c", "subj", "<p>body</p>") is False
            )


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
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Notify me"
        )
        email_service.notify_new_ticket(db_session, ticket)
        from sqlalchemy import select

        rows = list(db_session.scalars(select(EmailOutbox)).all())
        assert len(rows) >= 1
        assert rows[0].list_unsubscribe_url
        assert "/email/unsubscribe?token=" in rows[0].list_unsubscribe_url
        assert "/email/unsubscribe?token=" in rows[0].html_body

    def test_notify_new_ticket_from_staff_notifies_other_staff(
        self, db_session, project_with_members, staff_user
    ):
        from app.models.enums import UserRole

        other_staff = make_user(
            db_session,
            "staff2@test.local",
            first_name="Staff",
            last_name="Two",
            role=UserRole.STAFF,
            project=project_with_members,
        )
        other_staff.notify_new_ticket = True
        staff_user.notify_new_ticket = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Staff ticket"
        )
        email_service.notify_new_ticket(db_session, ticket)
        from sqlalchemy import select

        rows = list(db_session.scalars(select(EmailOutbox)).all())
        emails = {r.to_email for r in rows}
        assert staff_user.email.lower() not in emails
        assert other_staff.email.lower() in emails

    def test_notify_new_comment(
        self, db_session, project_with_members, client_user, staff_user
    ):
        staff_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Comment notify"
        )
        email_service.notify_new_comment(db_session, ticket, client_user.id)
        from sqlalchemy import select

        row = db_session.scalar(select(EmailOutbox))
        assert row is not None
        assert "/open/" in row.html_body
        assert "/login" in row.html_body

    def test_notify_internal_comment_unassigned_broadcasts_staff(
        self, db_session, project_with_members, staff_user, client_user
    ):
        other_staff = _staff_peer(
            db_session,
            project_with_members,
            "staff-internal-broadcast@test.local",
            first="Internal",
            last="Broadcast",
        )
        staff_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Internal"
        )
        email_service.notify_new_comment(
            db_session, ticket, staff_user.id, is_internal=True
        )
        emails = _outbox_emails(db_session)
        assert other_staff.email.lower() in emails
        assert staff_user.email.lower() not in emails
        assert client_user.email.lower() not in emails

    def test_notify_internal_comment_to_involved_admin(
        self, db_session, project_with_members, staff_user, admin_user
    ):
        project_service.add_project_member(
            db_session, project_with_members.id, admin_user.id
        )
        admin_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Internal assignee"
        )
        ticket_service.assign_ticket(db_session, ticket, staff_user, admin_user.id)
        ticket = ticket_service.get_ticket(db_session, ticket.id)
        assert ticket is not None
        email_service.notify_new_comment(
            db_session, ticket, staff_user.id, is_internal=True
        )
        from sqlalchemy import select

        rows = list(db_session.scalars(select(EmailOutbox)).all())
        assert any(r.to_email == admin_user.email.lower() for r in rows)

    def test_admin_author_respects_notify_new_ticket_pref(
        self, db_session, project_with_members, admin_user
    ):
        admin_user.notify_new_ticket = False
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, admin_user, title="Admin authored"
        )
        email_service.notify_new_ticket(db_session, ticket)
        from sqlalchemy import select

        rows = list(db_session.scalars(select(EmailOutbox)).all())
        assert all(r.to_email != admin_user.email.lower() for r in rows)

    def test_staff_recipients_dedupes_assignee(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Dedup"
        )
        ticket_service.assign_ticket(db_session, ticket, staff_user, staff_user.id)
        ticket = ticket_service.get_ticket(db_session, ticket.id)
        assert ticket is not None
        group = email_service._staff_recipients(db_session, ticket)
        assert sum(1 for u in group if u.id == staff_user.id) == 1

    def test_inactive_participant_skipped(
        self, db_session, project_with_members, client_user, staff_user
    ):
        staff_user.notify_reply = True
        staff_user.is_active = False
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Inactive"
        )
        email_service.notify_new_comment(db_session, ticket, client_user.id)
        from sqlalchemy import select

        assert db_session.scalar(select(EmailOutbox)) is None

    def test_admin_without_membership_no_ops_mail(
        self, db_session, project_with_members, client_user, admin_user
    ):
        admin_user.notify_new_ticket = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Admin skip"
        )
        email_service.notify_new_ticket(db_session, ticket)
        from sqlalchemy import select

        rows = list(db_session.scalars(select(EmailOutbox)).all())
        assert all(r.to_email != admin_user.email.lower() for r in rows)

    def test_notify_uses_recipient_ui_lang(
        self, db_session, project_with_members, client_user, staff_user
    ):
        staff_user.notify_new_ticket = True
        staff_user.ui_lang = "pl"
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Lang"
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
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Update"
        )
        email_service.notify_ticket_update(
            db_session, ticket, staff_user.id, change_key="enums.ticket_status.DONE"
        )
        from sqlalchemy import select

        assert db_session.scalar(select(EmailOutbox)) is not None

    def test_notify_assignment(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Assign"
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


class TestCommentRecipients:
    def test_notifies_client_participant_when_other_client_comments(
        self, db_session, project_with_members, client_user
    ):
        ticket, peer = peer_participant_ticket(
            db_session, project_with_members, client_user
        )
        email_service.notify_new_comment(db_session, ticket, client_user.id)
        assert peer.email.lower() in _outbox_emails(db_session)

    def test_notifies_staff_participant_when_other_staff_comments(
        self, db_session, project_with_members, staff_user
    ):
        other_staff = _staff_peer(
            db_session,
            project_with_members,
            "staff-peer@test.local",
            first="Staff",
            last="Peer",
        )
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Staff peer"
        )
        ticket_service.add_participant(db_session, ticket, staff_user, other_staff.id)
        ticket = ticket_service.get_ticket(db_session, ticket.id)
        assert ticket is not None
        staff_user.notify_reply = True
        db_session.commit()
        email_service.notify_new_comment(db_session, ticket, staff_user.id)
        assert other_staff.email.lower() in _outbox_emails(db_session)

    def test_internal_comment_skips_client_participant(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket, peer = peer_participant_ticket(
            db_session, project_with_members, client_user
        )
        staff_user.notify_reply = True
        db_session.commit()
        email_service.notify_new_comment(
            db_session, ticket, staff_user.id, is_internal=True
        )
        assert peer.email.lower() not in _outbox_emails(db_session)

    def test_comment_skips_author(
        self, db_session, project_with_members, client_user, staff_user
    ):
        staff_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Author skip"
        )
        email_service.notify_new_comment(db_session, ticket, client_user.id)
        assert client_user.email.lower() not in _outbox_emails(db_session)

    def test_unwatch_url_only_for_participants(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket, peer = peer_participant_ticket(
            db_session, project_with_members, client_user
        )
        staff_user.notify_reply = True
        db_session.commit()
        email_service.notify_new_comment(db_session, ticket, client_user.id)
        rows = list(db_session.scalars(select(EmailOutbox)).all())
        peer_row = next(r for r in rows if r.to_email == peer.email.lower())
        staff_row = next(r for r in rows if r.to_email == staff_user.email.lower())
        assert "/email/unwatch" in peer_row.html_body
        assert "/email/unwatch" not in staff_row.html_body

    def test_client_comment_with_assignee_skips_other_staff(
        self, db_session, project_with_members, client_user, staff_user
    ):
        other_staff = _staff_peer(
            db_session, project_with_members, "staff-other-reply@test.local"
        )
        staff_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Assigned reply"
        )
        ticket_service.assign_ticket(db_session, ticket, staff_user, staff_user.id)
        ticket = ticket_service.get_ticket(db_session, ticket.id)
        assert ticket is not None
        email_service.notify_new_comment(db_session, ticket, client_user.id)
        emails = _outbox_emails(db_session)
        assert staff_user.email.lower() in emails
        assert other_staff.email.lower() not in emails

    def test_client_comment_without_assignee_broadcasts_staff(
        self, db_session, project_with_members, client_user, staff_user
    ):
        other_staff = _staff_peer(
            db_session,
            project_with_members,
            "staff-broadcast@test.local",
            first="Broadcast",
        )
        staff_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Unassigned reply"
        )
        email_service.notify_new_comment(db_session, ticket, client_user.id)
        emails = _outbox_emails(db_session)
        assert staff_user.email.lower() in emails
        assert other_staff.email.lower() in emails

    def test_assignee_comment_does_not_broadcast_staff(
        self, db_session, project_with_members, client_user, staff_user
    ):
        other_staff = _staff_peer(
            db_session,
            project_with_members,
            "staff-no-broadcast@test.local",
            first="No",
            last="Broadcast",
        )
        client_user.notify_reply = True
        staff_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Assignee replies"
        )
        ticket_service.assign_ticket(db_session, ticket, staff_user, staff_user.id)
        ticket = ticket_service.get_ticket(db_session, ticket.id)
        assert ticket is not None
        email_service.notify_new_comment(db_session, ticket, staff_user.id)
        emails = _outbox_emails(db_session)
        assert client_user.email.lower() in emails
        assert other_staff.email.lower() not in emails
        assert staff_user.email.lower() not in emails

    def test_internal_with_assignee_skips_other_staff(
        self, db_session, project_with_members, client_user, staff_user
    ):
        other_staff = _staff_peer(
            db_session,
            project_with_members,
            "staff-internal-skip@test.local",
            first="Internal",
            last="Skip",
        )
        staff_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Internal assigned"
        )
        ticket_service.assign_ticket(db_session, ticket, staff_user, staff_user.id)
        ticket = ticket_service.get_ticket(db_session, ticket.id)
        assert ticket is not None
        email_service.notify_new_comment(
            db_session, ticket, other_staff.id, is_internal=True
        )
        emails = _outbox_emails(db_session)
        assert staff_user.email.lower() in emails
        assert other_staff.email.lower() not in emails
        assert client_user.email.lower() not in emails

    def test_internal_notifies_staff_participant(
        self, db_session, project_with_members, client_user, staff_user
    ):
        watcher = _staff_peer(
            db_session,
            project_with_members,
            "staff-internal-watch@test.local",
            first="Watch",
        )
        staff_user.notify_reply = True
        db_session.commit()
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Internal watcher"
        )
        ticket_service.assign_ticket(db_session, ticket, staff_user, staff_user.id)
        ticket_service.add_participant(db_session, ticket, staff_user, watcher.id)
        ticket = ticket_service.get_ticket(db_session, ticket.id)
        assert ticket is not None
        email_service.notify_new_comment(
            db_session, ticket, staff_user.id, is_internal=True
        )
        emails = _outbox_emails(db_session)
        assert watcher.email.lower() in emails
        assert staff_user.email.lower() not in emails
        assert client_user.email.lower() not in emails
