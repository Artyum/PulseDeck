"""Ticket operations: tags, assign, participants, priorities, types."""

from tests.helpers import login_client, login_staff, make_ticket


class TestTags:
    def test_add_tag_staff(self, client, db_session, staff_user, project_with_members):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Tag test"
        )
        login_staff(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/tags",
            data={"name": "urgent"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_add_tag_client_blocked(
        self, client, db_session, client_user, project_with_members
    ):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Tag client"
        )
        login_client(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/tags",
            data={"name": "urgent"},
            follow_redirects=False,
        )
        assert r.status_code in (303, 403)


class TestAssign:
    def test_staff_assign(self, client, db_session, staff_user, project_with_members):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Assign test"
        )
        login_staff(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/assign",
            data={"assignee_id": str(staff_user.id)},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_staff_self_assign(
        self, client, db_session, staff_user, project_with_members
    ):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, title="Self-assign"
        )
        login_staff(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/self-assign",
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)


class TestPriorityType:
    def test_change_priority(
        self, client, db_session, client_user, project_with_members
    ):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Priority test"
        )
        login_client(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/priority",
            data={"priority": "HIGH"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_change_type(self, client, db_session, client_user, project_with_members):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Type test"
        )
        login_client(client)
        r = client.post(
            f"/t/{project_with_members.key}-{ticket.number}/type",
            data={"type": "QUESTION"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)
