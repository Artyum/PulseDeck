"""Tests for ticket permission functions using DB fixtures.

Permission functions need a real DB to resolve project membership,
so we use the existing integration fixtures.
"""

from app.models.enums import TicketStatus
from app.services import tickets as ticket_service
from tests.helpers import make_ticket, make_user


def _reload_ticket(db, ticket_id: int):
    ticket = ticket_service.get_ticket(db, ticket_id)
    assert ticket is not None
    return ticket


class TestCanComment:
    def test_open_ticket_member(self, db_session, project_with_members, client_user):
        ticket = make_ticket(db_session, project_with_members, client_user)
        assert ticket_service.can_comment(db_session, client_user, ticket) is True

    def test_non_member_cannot(
        self, db_session, project_with_members, admin_user, client_user
    ):
        """Non-member user (not admin) cannot comment."""
        non_member = make_user(
            db_session,
            "nonmember@test.local",
            first_name="Non",
            last_name="Member",
            password="Test1234!abcd",
        )

        ticket = make_ticket(db_session, project_with_members, client_user)
        assert ticket_service.can_comment(db_session, non_member, ticket) is False

    def test_done_ticket_blocked(self, db_session, project_with_members, client_user):
        ticket = make_ticket(
            db_session, project_with_members, client_user, status=TicketStatus.DONE
        )
        assert ticket_service.can_comment(db_session, client_user, ticket) is False


class TestCanAssign:
    def test_staff_member_can(self, db_session, project_with_members, staff_user):
        ticket = make_ticket(db_session, project_with_members, staff_user)
        assert ticket_service.can_assign(staff_user, ticket, db_session) is True

    def test_client_cannot(self, db_session, project_with_members, client_user):
        ticket = make_ticket(db_session, project_with_members, client_user)
        assert ticket_service.can_assign(client_user, ticket, db_session) is False

    def test_assign_staff_or_admin(
        self, db_session, project_with_members, admin_user, staff_user
    ):
        ticket = make_ticket(db_session, project_with_members, staff_user)
        assert ticket_service.can_assign(admin_user, ticket, db_session) is True
        assert ticket_service.can_assign(staff_user, ticket, db_session) is True


class TestCanSetDone:
    def test_staff_member_can(self, db_session, project_with_members, staff_user):
        ticket = make_ticket(db_session, project_with_members, staff_user)
        assert ticket_service.can_set_done(staff_user, ticket, db_session) is True

    def test_author_client_can(self, db_session, project_with_members, client_user):
        ticket = make_ticket(db_session, project_with_members, client_user)
        assert ticket_service.can_set_done(client_user, ticket, db_session) is True

    def test_non_author_client_cannot(
        self, db_session, project_with_members, client_user
    ):
        """Only one client_user; create ticket as staff, then test client"""
        ticket = make_ticket(db_session, project_with_members, client_user)
        # Use a *different* client (client_user is author, so can_set_done works)
        # Create another user to verify non-author cannot
        other = make_user(
            db_session,
            "other2@test.local",
            first_name="Other",
            last_name="User",
            project=project_with_members,
        )

        ticket = make_ticket(db_session, project_with_members, other)
        assert ticket_service.can_set_done(client_user, ticket, db_session) is False


class TestCanReopen:
    def test_done_ticket_staff_can(self, db_session, project_with_members, staff_user):
        ticket = make_ticket(
            db_session, project_with_members, staff_user, status=TicketStatus.DONE
        )
        assert ticket_service.can_reopen(staff_user, ticket, db_session) is True

    def test_non_done_ticket_cannot(self, db_session, project_with_members, staff_user):
        ticket = make_ticket(db_session, project_with_members, staff_user)
        assert ticket_service.can_reopen(staff_user, ticket, db_session) is False

    def test_client_within_deadline(
        self, db_session, project_with_members, client_user
    ):

        ticket = make_ticket(
            db_session, project_with_members, client_user, status=TicketStatus.DONE
        )
        assert ticket_service.can_reopen(client_user, ticket, db_session) is True


class TestCanEditTicket:
    def test_staff_author_grace(self, db_session, project_with_members, staff_user):
        ticket = make_ticket(db_session, project_with_members, staff_user)
        assert ticket_service.can_edit_ticket(staff_user, ticket, db_session) is True

    def test_staff_non_author_cannot_edit_content(
        self, db_session, project_with_members, staff_user, client_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        assert ticket_service.can_edit_ticket(staff_user, ticket, db_session) is False

    def test_author_grace_until_comment(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        assert ticket_service.can_edit_ticket(client_user, ticket, db_session) is True
        ticket_service.add_comment(
            db_session, ticket, staff_user, "note", is_internal=True
        )
        ticket = _reload_ticket(db_session, ticket.id)
        assert ticket_service.can_edit_ticket(client_user, ticket, db_session) is False

    def test_grace_comment_locked_when_ticket_locked(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        c1 = ticket_service.add_comment(db_session, ticket, client_user, "first")
        ticket = _reload_ticket(db_session, ticket.id)
        assert ticket.author_edits_locked_at is not None
        assert (
            ticket_service.can_edit_comment(db_session, client_user, ticket, c1)
            is False
        )
        assert ticket_service.can_edit_ticket(client_user, ticket, db_session) is False
        assert (
            ticket_service.can_edit_comment(db_session, staff_user, ticket, c1) is False
        )

    def test_admin_can_moderate_without_membership(
        self, db_session, project_with_members, client_user, admin_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        assert ticket_service.can_edit_ticket(admin_user, ticket, db_session) is True
        assert ticket_service.can_delete_ticket(admin_user, ticket) is True
        assert ticket_service.can_assign(admin_user, ticket, db_session) is True
        assert ticket_service.can_comment(db_session, admin_user, ticket) is True
        updated = ticket_service.set_status(
            db_session,
            ticket,
            admin_user,
            TicketStatus.IN_PROGRESS,
        )
        assert updated.status == TicketStatus.IN_PROGRESS

    def test_unassign_keeps_author_edit_lock(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        ticket_service.assign_ticket(db_session, ticket, staff_user, staff_user.id)
        ticket = _reload_ticket(db_session, ticket.id)
        assert ticket.author_edits_locked_at is not None
        ticket_service.assign_ticket(db_session, ticket, staff_user, None)
        ticket = _reload_ticket(db_session, ticket.id)
        assert ticket.author_edits_locked_at is not None
        assert ticket_service.can_edit_ticket(client_user, ticket, db_session) is False

    def test_soft_delete_hides_from_non_admin(
        self, db_session, project_with_members, client_user, staff_user, admin_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        ticket_service.soft_delete_ticket(db_session, ticket, admin_user)
        ticket = _reload_ticket(db_session, ticket.id)
        assert ticket.deleted_at is not None
        assert ticket_service.can_view_ticket(db_session, client_user, ticket) is False
        assert ticket_service.can_view_ticket(db_session, staff_user, ticket) is False
        assert ticket_service.can_view_ticket(db_session, admin_user, ticket) is True
        listed = ticket_service.list_tickets(
            db_session, project_with_members.id, user=staff_user, mine=False
        )
        assert all(t.id != ticket.id for t in listed.items)
        listed_admin = ticket_service.list_tickets(
            db_session, project_with_members.id, user=admin_user, mine=False
        )
        assert any(t.id == ticket.id for t in listed_admin.items)

    def test_participant_client_can_comment(
        self, db_session, project_with_members, client_user, staff_user
    ):
        other = make_user(
            db_session,
            "participant@test.local",
            first_name="Part",
            last_name="Client",
            project=project_with_members,
        )
        ticket = make_ticket(db_session, project_with_members, client_user)
        assert ticket_service.can_comment(db_session, other, ticket) is False
        ticket_service.add_participant(db_session, ticket, client_user, other.id)
        ticket = _reload_ticket(db_session, ticket.id)
        assert ticket_service.can_comment(db_session, other, ticket) is True


class TestCanViewTicket:
    def test_client_member_sees_all_project_tickets(
        self, db_session, project_with_members, client_user, staff_user
    ):
        other = make_user(
            db_session,
            "viewer@test.local",
            first_name="View",
            last_name="Client",
            project=project_with_members,
        )
        ticket = make_ticket(db_session, project_with_members, staff_user)
        assert ticket_service.can_view_ticket(db_session, other, ticket) is True


class TestGetTicketPermissions:
    def test_staff_permissions(self, db_session, project_with_members, staff_user):
        ticket = make_ticket(db_session, project_with_members, staff_user)
        perms = ticket_service.get_ticket_permissions(db_session, staff_user, ticket)
        assert perms.can_assign is True
        assert perms.can_set_done is True
        assert perms.can_edit is True
        assert perms.can_comment is True
        assert perms.can_delete_ticket is False

    def test_client_permissions(self, db_session, project_with_members, client_user):
        ticket = make_ticket(db_session, project_with_members, client_user)
        perms = ticket_service.get_ticket_permissions(db_session, client_user, ticket)
        assert perms.can_assign is False
        assert perms.can_comment is True
        assert perms.can_edit is True
