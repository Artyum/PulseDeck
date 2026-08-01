from datetime import datetime, timezone

from app.models.enums import TicketType
from app.services import reply_token as reply_token_service
from app.services import tickets as ticket_service
from app.utils.urls import ticket_path


def _login(client, email: str, password: str, *, next_path: str | None = None):
    data = {"email": email, "password": password}
    if next_path is not None:
        data["next"] = next_path
    return client.post(
        "/auth/login",
        data=data,
        follow_redirects=False,
    )


class TestOpenReplyRoutes:
    def test_get_valid_shows_thread(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Open reply",
            description="Body",
            ticket_type=TicketType.BUG,
        )
        ticket_service.add_comment(
            db_session, ticket, client_user, "First note", is_internal=False
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        r = client.get(f"/open/{raw}")
        assert r.status_code == 200
        assert "Open reply" in r.text
        assert 'name="content"' in r.text
        assert "Klient T." in r.text
        assert "Klient Test" not in r.text
        assert "Zgłaszający" not in r.text and "Reporter" not in r.text
        assert "Obsługujący" not in r.text and "Assignee" not in r.text
        assert "data-attach-picker" not in r.text
        assert 'name="attachments"' not in r.text
        assert (
            "To attach a file, sign in to the portal." in r.text
            or "Aby dołączyć plik, zaloguj się w portalu." in r.text
        )
        assert f"/login?next={ticket_path(ticket)}" in r.text

    def test_login_next_redirects_to_ticket(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Login next",
            description="Body",
            ticket_type=TicketType.BUG,
        )
        dest = ticket_path(ticket)
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        r = client.get(f"/open/{raw}")
        assert f"/login?next={dest}" in r.text
        r = _login(client, "staff@test.local", "Staff123!", next_path=dest)
        assert r.status_code == 303
        assert r.headers["location"] == dest

    def test_get_used_status(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Used",
            description="Body",
            ticket_type=TicketType.BUG,
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        row = reply_token_service.lookup_reply_token(db_session, raw)
        assert row is not None
        row.used_at = datetime.now(timezone.utc)
        db_session.commit()
        r = client.get(f"/open/{raw}")
        assert r.status_code == 200
        assert "Link already used" in r.text or "Link już wykorzystany" in r.text

    def test_post_consumes_and_thanks(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Post reply",
            description="Body",
            ticket_type=TicketType.BUG,
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        r = client.post(
            f"/open/{raw}",
            data={"content": "Thanks from mail link"},
        )
        assert r.status_code == 200
        assert "Thank you" in r.text or "Dziękujemy" in r.text
        row = reply_token_service.lookup_reply_token(db_session, raw)
        assert row is not None
        assert row.used_at is not None
        r2 = client.get(f"/open/{raw}")
        assert r2.status_code == 200
        assert "Link already used" in r2.text or "Link już wykorzystany" in r2.text

    def test_owner_session_redirects_without_consume(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Owner redirect",
            description="Body",
            ticket_type=TicketType.BUG,
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        _login(client, "staff@test.local", "Staff123!")
        r = client.get(f"/open/{raw}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == ticket_path(ticket)
        row = reply_token_service.lookup_reply_token(db_session, raw)
        assert row is not None
        assert row.used_at is None

    def test_other_session_conflict(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Conflict",
            description="Body",
            ticket_type=TicketType.BUG,
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        _login(client, "client@test.local", "Client123!")
        r = client.get(f"/open/{raw}")
        assert r.status_code == 200
        assert "client@test.local" in r.text
        assert "staff@test.local" in r.text
