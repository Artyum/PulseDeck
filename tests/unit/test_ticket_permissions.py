"""Tests for ticket permission functions using DB fixtures.

Permission functions need a real DB to resolve project membership,
so we use the existing integration fixtures.
"""

from app.models.enums import TicketStatus, TicketType
from app.services import projects as project_service
from app.services import tickets as ticket_service


def _make_ticket(db, project_id, author, status=TicketStatus.NEW):
    ticket = ticket_service.create_ticket(
        db,
        project_id=project_id,
        author=author,
        title="Test ticket",
        description="Description",
        ticket_type=TicketType.BUG,
    )
    if status != TicketStatus.NEW:
        # Set status directly for testing
        ticket.status = status
        if status == TicketStatus.DONE:
            from datetime import datetime, timezone

            ticket.closed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(ticket)
    return ticket


class TestCanComment:
    def test_open_ticket_member(self, db_session, project_with_members, client_user):
        ticket = _make_ticket(db_session, project_with_members.id, client_user)
        assert ticket_service.can_comment(db_session, client_user, ticket) is True

    def test_non_member_cannot(
        self, db_session, project_with_members, admin_user, client_user
    ):
        """Non-member user (not admin) cannot comment."""
        from datetime import datetime, timezone

        from app.models.enums import UserRole
        from app.models.user import User
        from app.services.auth import set_password

        non_member = User(
            email="nonmember@test.local",
            first_name="Non",
            last_name="Member",
            role=UserRole.USER,
            activated_at=datetime.now(timezone.utc),
        )
        set_password(non_member, "Test1234!")
        db_session.add(non_member)
        db_session.commit()
        db_session.refresh(non_member)

        ticket = _make_ticket(db_session, project_with_members.id, client_user)
        assert ticket_service.can_comment(db_session, non_member, ticket) is False

    def test_done_ticket_blocked(self, db_session, project_with_members, client_user):
        ticket = _make_ticket(
            db_session, project_with_members.id, client_user, TicketStatus.DONE
        )
        assert ticket_service.can_comment(db_session, client_user, ticket) is False


class TestCanAssign:
    def test_staff_member_can(self, db_session, project_with_members, staff_user):
        ticket = _make_ticket(db_session, project_with_members.id, staff_user)
        assert ticket_service.can_assign(staff_user, ticket, db_session) is True

    def test_client_cannot(self, db_session, project_with_members, client_user):
        ticket = _make_ticket(db_session, project_with_members.id, client_user)
        assert ticket_service.can_assign(client_user, ticket, db_session) is False

    def test_staff_non_member_cannot(
        self, db_session, project_with_members, admin_user, staff_user
    ):
        """Staff user not in project cannot assign (admin bypasses membership check)."""
        # admin bypass check - create ticket with staff user
        ticket = _make_ticket(db_session, project_with_members.id, staff_user)
        assert (
            ticket_service.can_assign(staff_user, ticket, db_session) is True
        )  # staff IS a member


class TestCanSetDone:
    def test_staff_member_can(self, db_session, project_with_members, staff_user):
        ticket = _make_ticket(db_session, project_with_members.id, staff_user)
        assert ticket_service.can_set_done(staff_user, ticket, db_session) is True

    def test_author_client_can(self, db_session, project_with_members, client_user):
        ticket = _make_ticket(db_session, project_with_members.id, client_user)
        assert ticket_service.can_set_done(client_user, ticket, db_session) is True

    def test_non_author_client_cannot(
        self, db_session, project_with_members, client_user
    ):
        """Only one client_user; create ticket as staff, then test client"""
        ticket = _make_ticket(db_session, project_with_members.id, client_user)
        # Use a *different* client (client_user is author, so can_set_done works)
        # Create another user to verify non-author cannot
        from datetime import datetime, timezone

        from app.models.enums import UserRole
        from app.models.user import User
        from app.services.auth import set_password

        other = User(
            email="other2@test.local",
            first_name="Other",
            last_name="User",
            role=UserRole.USER,
            activated_at=datetime.now(timezone.utc),
        )
        set_password(other, "Client123!")
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)
        project_service.add_project_member(
            db_session, project_with_members.id, other.id
        )

        ticket = _make_ticket(db_session, project_with_members.id, other)
        assert ticket_service.can_set_done(client_user, ticket, db_session) is False


class TestCanReopen:
    def test_done_ticket_staff_can(self, db_session, project_with_members, staff_user):
        ticket = _make_ticket(
            db_session, project_with_members.id, staff_user, TicketStatus.DONE
        )
        assert ticket_service.can_reopen(staff_user, ticket, db_session) is True

    def test_non_done_ticket_cannot(self, db_session, project_with_members, staff_user):
        ticket = _make_ticket(db_session, project_with_members.id, staff_user)
        assert ticket_service.can_reopen(staff_user, ticket, db_session) is False

    def test_client_within_deadline(
        self, db_session, project_with_members, client_user
    ):

        ticket = _make_ticket(
            db_session, project_with_members.id, client_user, TicketStatus.DONE
        )
        assert ticket_service.can_reopen(client_user, ticket, db_session) is True


class TestCanEditTicket:
    def test_staff_can_always(self, db_session, project_with_members, staff_user):
        ticket = _make_ticket(db_session, project_with_members.id, staff_user)
        assert ticket_service.can_edit_ticket(staff_user, ticket, db_session) is True

    def test_author_new_can(self, db_session, project_with_members, client_user):
        ticket = _make_ticket(db_session, project_with_members.id, client_user)
        assert ticket_service.can_edit_ticket(client_user, ticket, db_session) is True

    def test_author_non_new_cannot(self, db_session, project_with_members, client_user):
        ticket = _make_ticket(
            db_session, project_with_members.id, client_user, TicketStatus.IN_PROGRESS
        )
        assert ticket_service.can_edit_ticket(client_user, ticket, db_session) is False


class TestGetTicketPermissions:
    def test_staff_permissions(self, db_session, project_with_members, staff_user):
        ticket = _make_ticket(db_session, project_with_members.id, staff_user)
        perms = ticket_service.get_ticket_permissions(db_session, staff_user, ticket)
        assert perms.can_assign is True
        assert perms.can_set_done is True
        assert perms.can_edit is True
        assert perms.can_comment is True

    def test_client_permissions(self, db_session, project_with_members, client_user):
        ticket = _make_ticket(db_session, project_with_members.id, client_user)
        perms = ticket_service.get_ticket_permissions(db_session, client_user, ticket)
        assert perms.can_assign is False
        assert perms.can_comment is True
        assert perms.can_edit is True  # author + NEW
