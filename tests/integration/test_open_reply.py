import re
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.session import get_db
from app.main import build_fastapi_app
from app.services import reply_token as reply_token_service
from app.services import tickets as ticket_service
from app.services.portal_settings import invalidate_cache
from app.utils.urls import ticket_path
from tests.helpers import login, login_client, login_staff, make_ticket


class TestOpenReplyRoutes:
    def test_get_valid_shows_thread(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="Open reply",
            description="Body",
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
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="Login next",
            description="Body",
        )
        dest = ticket_path(ticket)
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        r = client.get(f"/open/{raw}")
        assert f"/login?next={dest}" in r.text
        r = login(
            client, "staff@test.local", "Staff123!abcd", next_path=dest, assert_ok=False
        )
        assert r.status_code == 303
        assert r.headers["location"] == dest

    def test_get_used_status(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="Used",
            description="Body",
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
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="Post reply",
            description="Body",
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

    def test_post_with_form_csrf_token(
        self,
        monkeypatch,
        db_engine,
        db_session,
        project_with_members,
        client_user,
        staff_user,
    ):
        monkeypatch.setenv("SECURITY_CSRF_ENABLED", "true")
        get_settings.cache_clear()
        invalidate_cache()
        SessionLocal = sessionmaker(
            bind=db_engine, autoflush=False, autocommit=False, class_=Session
        )

        def _get_db():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app = build_fastapi_app()
        app.dependency_overrides[get_db] = _get_db
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="CSRF form reply",
            description="Body",
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        try:
            with TestClient(app) as csrf_client:
                page = csrf_client.get(f"/open/{raw}")
                assert page.status_code == 200
                match = re.search(
                    r'name="csrf_token" value="([^"]+)"',
                    page.text,
                )
                assert match is not None
                reply = csrf_client.post(
                    f"/open/{raw}",
                    data={
                        "csrf_token": match.group(1),
                        "content": "Reply protected by form CSRF",
                    },
                )
                assert reply.status_code == 200
                assert "Thank you" in reply.text or "Dziękujemy" in reply.text
        finally:
            app.dependency_overrides.clear()
            get_settings.cache_clear()

    def test_owner_session_redirects_without_consume(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="Owner redirect",
            description="Body",
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        login_staff(client)
        r = client.get(f"/open/{raw}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == ticket_path(ticket)
        row = reply_token_service.lookup_reply_token(db_session, raw)
        assert row is not None
        assert row.used_at is None

    def test_other_session_conflict(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="Conflict",
            description="Body",
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        login_client(client)
        r = client.get(f"/open/{raw}")
        assert r.status_code == 200
        assert "client@test.local" not in r.text
        assert "staff@test.local" not in r.text
        assert (
            "This link belongs to a different account" in r.text
            or "Ten odnośnik jest przypisany do innego konta" in r.text
        )

    def test_shows_only_last_comment_group(
        self, client, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="Trim thread",
            description="Ticket body stays",
        )
        ticket_service.add_comment(
            db_session, ticket, client_user, "OLD_CLIENT_NOTE", is_internal=False
        )
        ticket_service.add_comment(
            db_session, ticket, staff_user, "STAFF_LAST_A", is_internal=False
        )
        ticket_service.add_comment(
            db_session, ticket, staff_user, "STAFF_LAST_B", is_internal=False
        )
        raw = reply_token_service.create_reply_token(db_session, client_user, ticket)
        r = client.get(f"/open/{raw}")
        assert r.status_code == 200
        assert "Ticket body stays" in r.text
        assert "OLD_CLIENT_NOTE" not in r.text
        assert "STAFF_LAST_A" in r.text
        assert "STAFF_LAST_B" in r.text
        assert (
            "Earlier messages are hidden" in r.text
            or "Wcześniejsza korespondencja jest ukryta" in r.text
        )
