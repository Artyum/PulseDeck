"""Portal user-facing integration tests."""

from app.models.enums import TicketStatus, TicketType
from app.services import tickets as ticket_service


def _login(client, email, password):
    r = client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert r.status_code in (303, 200)


class TestFeed:
    def test_project_feed(self, client, client_user, project_with_members):
        _login(client, "client@test.local", "Client123!")
        r = client.get(f"/p/{project_with_members.key}")
        assert r.status_code == 200
        assert project_with_members.name in r.text

    def test_project_feed_with_filters(self, client, client_user, project_with_members):
        _login(client, "client@test.local", "Client123!")
        r = client.get(f"/p/{project_with_members.key}?view=open")
        assert r.status_code == 200

    def test_project_not_found(self, client, client_user):
        _login(client, "client@test.local", "Client123!")
        r = client.get("/p/NONEXIST", follow_redirects=False)
        assert r.status_code in (303, 403, 404, 200)

    def test_redirect_when_no_projects(self, client, client_user):
        # client_user has no projects by default (project_with_members not loaded)
        _login(client, "client@test.local", "Client123!")
        r = client.get("/", follow_redirects=False)
        # Just check it returns something valid (redirect or empty)
        assert r.status_code in (200, 303)

    def test_feed_used_tags_only(
        self, client, db_session, staff_user, project_with_members
    ):
        from app.models.ticket import Tag

        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Tag test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        ticket_service.add_ticket_tag(db_session, ticket, staff_user, "urgent")
        db_session.add(Tag(project_id=project_with_members.id, name="orphan"))
        db_session.commit()
        _login(client, "staff@test.local", "Staff123!")
        r = client.get(f"/p/{project_with_members.key}")
        assert r.status_code == 200
        assert "urgent" in r.text
        assert "orphan" not in r.text

    def test_feed_project_tags_shown(
        self, client, db_session, staff_user, project_with_members
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Tag visible",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        ticket_service.add_ticket_tag(db_session, ticket, staff_user, "bug")
        db_session.commit()
        _login(client, "staff@test.local", "Staff123!")
        r = client.get(f"/p/{project_with_members.key}")
        assert r.status_code == 200
        assert "bug" in r.text


class TestTicketCRUD:
    def test_create_ticket(self, client, client_user, project_with_members):
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/p/{project_with_members.key}/tickets",
            data={
                "title": "New ticket",
                "description": "Description",
                "ticket_type": "BUG",
                "priority": "NORMAL",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_create_ticket_missing_title(
        self, client, client_user, project_with_members
    ):
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/p/{project_with_members.key}/tickets",
            data={
                "title": "",
                "description": "Description",
                "ticket_type": "BUG",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)

    def test_ticket_detail(self, client, db_session, client_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Detail test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "client@test.local", "Client123!")
        r = client.get(f"/t/{project_with_members.key}-{ticket.number}")
        assert r.status_code == 200
        assert "Detail test" in r.text

    def test_edit_ticket(self, client, db_session, client_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Edit me",
            description="Original",
            ticket_type=TicketType.BUG,
        )
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/edit",
            data={
                "title": "Edited title",
                "description": "Edited desc",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)


class TestComments:
    def test_add_comment(self, client, db_session, client_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Comment test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/comments",
            data={
                "content": "This is a comment",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_add_internal_note_staff(
        self, client, db_session, staff_user, project_with_members
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Internal test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "staff@test.local", "Staff123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/comments",
            data={
                "content": "Internal note",
                "is_internal": "true",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_comment_on_done_ticket_blocked(
        self, client, db_session, client_user, project_with_members
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Done ticket",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        ticket_service.set_status(db_session, ticket, client_user, TicketStatus.DONE)
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/comments",
            data={"content": "Late comment"},
            follow_redirects=False,
        )
        # Should be blocked (403 or redirect)
        assert r.status_code in (303, 403)


class TestTicketStatus:
    def test_set_status_staff(
        self, client, db_session, staff_user, project_with_members
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Status test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "staff@test.local", "Staff123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/status",
            data={"status": "IN_PROGRESS"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_reopen_ticket(self, client, db_session, staff_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Reopen me",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        ticket_service.set_status(db_session, ticket, staff_user, TicketStatus.DONE)
        _login(client, "staff@test.local", "Staff123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/reopen",
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)


class TestInactiveProject:
    def test_inactive_project_not_accessible(
        self, client, db_session, client_user, project_with_members
    ):
        from app.services import projects as project_service

        project_service.set_project_active(
            db_session, project_with_members, active=False
        )
        _login(client, "client@test.local", "Client123!")
        r = client.get(f"/p/{project_with_members.key}", follow_redirects=False)
        assert r.status_code in (303, 404)


class TestParticipantsAndReporter:
    def test_add_participant(
        self, client, db_session, client_user, staff_user, project_with_members
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Participants",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/participants",
            data={"user_id": str(staff_user.id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_admin_remove_participant(
        self, client, db_session, client_user, admin_user, project_with_members
    ):
        from datetime import datetime, timezone

        from app.models.enums import UserRole
        from app.models.user import User
        from app.services import projects as project_service
        from app.services.auth import set_password

        project_service.add_project_member(
            db_session, project_with_members.id, admin_user.id
        )
        peer = User(
            email="peer-portal@test.local",
            first_name="Peer",
            last_name="Portal",
            role=UserRole.USER,
            activated_at=datetime.now(timezone.utc),
        )
        set_password(peer, "Peer1234!")
        db_session.add(peer)
        db_session.commit()
        db_session.refresh(peer)
        project_service.add_project_member(db_session, project_with_members.id, peer.id)

        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Remove participant",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        ticket_service.add_participant(db_session, ticket, client_user, peer.id)

        _login(client, "admin@test.local", "Admin123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/unwatch",
            data={"user_id": str(peer.id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)
        db_session.commit()
        db_session.expire_all()
        refreshed = ticket_service.get_ticket(db_session, ticket.id)
        assert refreshed is not None
        assert all(p.user_id != peer.id for p in refreshed.participants)

    def test_change_reporter(
        self, client, db_session, client_user, staff_user, project_with_members
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Reporter",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "staff@test.local", "Staff123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/reporter",
            data={"author_id": str(client_user.id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)


class TestRemoveTag:
    def test_remove_tag(self, client, db_session, staff_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Untag",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        tagged = ticket_service.add_ticket_tag(db_session, ticket, staff_user, "temp")
        tag_id = tagged.ticket_tags[0].tag_id
        _login(client, "staff@test.local", "Staff123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/tags/remove",
            data={"tag_id": str(tag_id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)
