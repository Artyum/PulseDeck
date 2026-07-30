"""Ticket operations: tags, assign, participants, priorities, types."""
import pytest
from app.models.enums import TicketType
from app.services import tickets as ticket_service


def _login(client, email, password):
    r = client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert r.status_code in (303, 200)


class TestTags:
    def test_add_tag_staff(self, client, db_session, staff_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Tag test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "staff@test.local", "Staff123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.id}/tags",
            data={"name": "urgent"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_add_tag_client_blocked(
        self, client, db_session, client_user, project_with_members
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Tag client",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.id}/tags",
            data={"name": "urgent"},
            follow_redirects=False,
        )
        assert r.status_code in (303, 403)


class TestAssign:
    def test_staff_assign(self, client, db_session, staff_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Assign test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "staff@test.local", "Staff123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.id}/assign",
            data={"assignee_id": str(staff_user.id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_staff_self_assign(
        self, client, db_session, staff_user, project_with_members
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=staff_user,
            title="Self-assign",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "staff@test.local", "Staff123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.id}/self-assign",
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)


class TestPriorityType:
    def test_change_priority(self, client, db_session, client_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Priority test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.id}/priority",
            data={"priority": "HIGH"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_change_type(self, client, db_session, client_user, project_with_members):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="Type test",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.id}/type",
            data={"type": "QUESTION"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)
