"""Tests for per-project ticket numbering."""

from app.models.enums import TicketType
from app.services import projects as project_service
from app.services import tickets as ticket_service


def test_numbers_start_at_one_per_project(db_session, client_user):
    project_a = project_service.create_project(db_session, "Alpha", "AAA")
    project_b = project_service.create_project(db_session, "Beta", "BBB")

    a1 = ticket_service.create_ticket(
        db_session,
        project_id=project_a.id,
        author=client_user,
        title="A1",
        description="d",
        ticket_type=TicketType.BUG,
    )
    a2 = ticket_service.create_ticket(
        db_session,
        project_id=project_a.id,
        author=client_user,
        title="A2",
        description="d",
        ticket_type=TicketType.BUG,
    )
    b1 = ticket_service.create_ticket(
        db_session,
        project_id=project_b.id,
        author=client_user,
        title="B1",
        description="d",
        ticket_type=TicketType.BUG,
    )

    assert a1.number == 1
    assert a2.number == 2
    assert b1.number == 1
    found = ticket_service.get_ticket_by_project_number(db_session, project_a.id, 2)
    assert found is not None
    assert found.id == a2.id
