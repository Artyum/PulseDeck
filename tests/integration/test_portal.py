"""Portal user-facing integration tests."""

from app.models.enums import TicketStatus
from app.services import tickets as ticket_service
from tests.helpers import login_admin, login_client, login_staff, make_ticket, make_user


class TestFeed:
    def test_project_feed(self, client, client_user, project_with_members):
        login_client(client)
        r = client.get(f"/p/{project_with_members.key}")
        assert r.status_code == 200
        assert project_with_members.name in r.text

    def test_project_feed_with_filters(self, client, client_user, project_with_members):
        login_client(client)
        r = client.get(f"/p/{project_with_members.key}?view=waiting_on_me")
        assert r.status_code == 200

    def test_project_not_found(self, client, client_user):
        login_client(client)
        r = client.get("/p/NONEXIST", follow_redirects=False)
        assert r.status_code in (303, 403, 404, 200)

    def test_redirect_when_no_projects(self, client, client_user):
        # client_user has no projects by default (project_with_members not loaded)
        login_client(client)
        r = client.get("/", follow_redirects=False)
        # Just check it returns something valid (redirect or empty)
        assert r.status_code in (200, 303)

    def test_feed_used_tags_only(
        self, client, db_session, staff_user, project_with_members
    ):
        from app.models.ticket import Tag

        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Tag test"
        )
        ticket_service.add_ticket_tag(db_session, ticket, staff_user, "urgent")
        db_session.add(Tag(project_id=project_with_members.id, name="orphan"))
        db_session.commit()
        login_staff(client)
        r = client.get(f"/p/{project_with_members.key}")
        assert r.status_code == 200
        assert "urgent" in r.text
        assert "orphan" not in r.text

    def test_feed_project_tags_shown(
        self, client, db_session, staff_user, project_with_members
    ):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Tag visible"
        )
        ticket_service.add_ticket_tag(db_session, ticket, staff_user, "bug")
        db_session.commit()
        login_staff(client)
        r = client.get(f"/p/{project_with_members.key}")
        assert r.status_code == 200
        assert "bug" in r.text


class TestTicketCRUD:
    def test_create_ticket(self, client, client_user, project_with_members):
        login_client(client)
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
        login_client(client)
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
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Detail test"
        )
        login_client(client)
        r = client.get(f"/t/{project_with_members.key}-{ticket.number}")
        assert r.status_code == 200
        assert "Detail test" in r.text

    def test_edit_ticket(self, client, db_session, client_user, project_with_members):
        ticket = make_ticket(
            db_session,
            project_with_members,
            client_user,
            title="Edit me",
            description="Original",
        )
        login_client(client)
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
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Comment test"
        )
        login_client(client)
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
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Internal test"
        )
        login_staff(client)
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
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Done ticket"
        )
        ticket_service.set_status(db_session, ticket, client_user, TicketStatus.DONE)
        login_client(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/comments",
            data={"content": "Late comment"},
            follow_redirects=False,
        )
        # Should be blocked (403 or redirect)
        assert r.status_code in (303, 403)

    def test_stale_reply_returns_409_keeps_draft(
        self, client, db_session, client_user, project_with_members
    ):
        import re

        from sqlalchemy import func, select

        from app.models.ticket import Comment
        from tests.helpers import login

        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Stale race"
        )
        first = ticket_service.add_comment(
            db_session, ticket, client_user, "First reply"
        )
        other = make_user(
            db_session,
            "other-stale@test.local",
            project=project_with_members,
        )
        ticket_service.add_participant(db_session, ticket, client_user, other.id)
        login(client, other.email, "Client123!ab")
        path = f"/t/{project_with_members.key}-{ticket.number}/comments"
        r = client.post(
            path,
            data={"content": "My draft reply", "seen_comment_id": "0"},
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )
        assert r.status_code == 409
        assert r.headers.get("X-PD-Stale-Thread") == "1"
        assert "My draft reply" in r.text
        assert "First reply" in r.text
        assert re.search(
            rf'name="seen_comment_id"\s+value="{first.id}"',
            r.text,
        )
        count = db_session.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.ticket_id == ticket.id)
        )
        assert count == 1

        r2 = client.post(
            path,
            data={"content": "My draft reply", "seen_comment_id": str(first.id)},
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )
        assert r2.status_code == 200
        assert "My draft reply" in r2.text
        count = db_session.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.ticket_id == ticket.id)
        )
        assert count == 2

    def test_internal_note_does_not_stale_client(
        self, client, db_session, client_user, staff_user, project_with_members
    ):
        from sqlalchemy import func, select

        from app.models.ticket import Comment

        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Internal invisible"
        )
        ticket_service.add_comment(
            db_session,
            ticket,
            staff_user,
            "Secret staff note",
            is_internal=True,
        )
        login_client(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/comments",
            data={"content": "Client reply", "seen_comment_id": "0"},
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )
        assert r.status_code == 200
        assert "Client reply" in r.text
        assert "Secret staff note" not in r.text
        count = db_session.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.ticket_id == ticket.id)
        )
        assert count == 2


class TestTicketStatus:
    def test_set_status_staff(
        self, client, db_session, staff_user, project_with_members
    ):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Status test"
        )
        login_staff(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/status",
            data={"status": "IN_PROGRESS"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_reopen_ticket(self, client, db_session, staff_user, project_with_members):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Reopen me"
        )
        ticket_service.set_status(db_session, ticket, staff_user, TicketStatus.DONE)
        login_staff(client)
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
        login_client(client)
        r = client.get(f"/p/{project_with_members.key}", follow_redirects=False)
        assert r.status_code in (303, 404)


class TestParticipantsAndReporter:
    def test_add_participant_client_adds_client(
        self, client, db_session, client_user, project_with_members
    ):
        peer = make_user(
            db_session,
            "peer-portal-add@test.local",
            first_name="Peer",
            last_name="PortalAdd",
            password="Peer1234!abcd",
            project=project_with_members,
        )
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Participants"
        )
        login_client(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/participants",
            data={"user_id": str(peer.id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_add_participant_client_cannot_add_staff(
        self, client, db_session, client_user, staff_user, project_with_members
    ):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Participants staff"
        )
        login_client(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/participants",
            data={"user_id": str(staff_user.id)},
            follow_redirects=False,
        )
        assert r.status_code == 400

    def test_admin_remove_participant(
        self, client, db_session, client_user, admin_user, project_with_members
    ):
        from app.services import projects as project_service

        project_service.add_project_member(
            db_session, project_with_members.id, admin_user.id
        )
        peer = make_user(
            db_session,
            "peer-portal@test.local",
            first_name="Peer",
            last_name="Portal",
            password="Peer1234!abcd",
            project=project_with_members,
        )
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Remove participant"
        )
        ticket_service.add_participant(db_session, ticket, client_user, peer.id)

        login_admin(client)
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
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Reporter"
        )
        login_staff(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/reporter",
            data={"author_id": str(client_user.id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)


class TestRemoveTag:
    def test_remove_tag(self, client, db_session, staff_user, project_with_members):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Untag"
        )
        tagged = ticket_service.add_ticket_tag(db_session, ticket, staff_user, "temp")
        tag_id = tagged.ticket_tags[0].tag_id
        login_staff(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/tags/remove",
            data={"tag_id": str(tag_id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)


class TestAclVisibility:
    def test_client_opens_other_members_ticket(
        self, client, db_session, client_user, staff_user, project_with_members
    ):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Staff only title"
        )
        login_client(client)
        r = client.get(f"/t/{project_with_members.key}-{ticket.number}")
        assert r.status_code == 200
        assert "Staff only title" in r.text

    def test_admin_creates_ticket_without_membership(
        self, client, admin_user, project_with_members
    ):
        login_admin(client)
        r = client.post(
            f"/p/{project_with_members.key}/tickets",
            data={
                "title": "Admin ticket",
                "description": "From admin",
                "ticket_type": "BUG",
                "priority": "NORMAL",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)
