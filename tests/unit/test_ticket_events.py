from app.models.enums import TicketEventType, TicketStatus
from app.services import ticket_events as event_service
from app.services import tickets as ticket_service
from tests.helpers import make_ticket, make_user


def _types(db, ticket, *, staff: bool):
    return [
        ev.event_type
        for ev in event_service.list_ticket_events(db, ticket, staff=staff)
    ]


class TestTicketEventLogging:
    def test_create_ticket_logs_created(
        self, db_session, project_with_members, client_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        types = _types(db_session, ticket, staff=False)
        assert types == [TicketEventType.CREATED]
        events = event_service.list_ticket_events(db_session, ticket, staff=False)
        assert events[0].actor_id == client_user.id
        payload = events[0].payload
        assert payload is not None
        assert payload["type"] == ticket.type.value
        assert payload["priority"] == ticket.priority.value

    def test_set_status_logs_change(
        self, db_session, project_with_members, staff_user, client_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        ticket_service.set_status(
            db_session, ticket, staff_user, TicketStatus.IN_PROGRESS
        )
        events = event_service.list_ticket_events(db_session, ticket, staff=True)
        status_ev = next(
            ev for ev in events if ev.event_type == TicketEventType.STATUS_CHANGED
        )
        assert status_ev.payload == {
            "from": TicketStatus.NEW.value,
            "to": TicketStatus.IN_PROGRESS.value,
        }
        assert status_ev.actor_id == staff_user.id

    def test_set_status_noop_skips_event(
        self, db_session, project_with_members, staff_user, client_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        before = len(event_service.list_ticket_events(db_session, ticket, staff=True))
        ticket_service.set_status(db_session, ticket, staff_user, TicketStatus.NEW)
        after = len(event_service.list_ticket_events(db_session, ticket, staff=True))
        assert after == before

    def test_internal_comment_hidden_from_client(
        self, db_session, project_with_members, staff_user, client_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        ticket_service.add_comment(
            db_session,
            ticket,
            staff_user,
            "Secret note",
            is_internal=True,
        )
        staff_types = _types(db_session, ticket, staff=True)
        client_types = _types(db_session, ticket, staff=False)
        assert TicketEventType.COMMENT_ADDED_INTERNAL in staff_types
        assert TicketEventType.COMMENT_ADDED_INTERNAL not in client_types
        assert TicketEventType.COMMENT_ADDED not in staff_types

    def test_public_comment_visible_to_all(
        self, db_session, project_with_members, client_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        ticket_service.add_comment(db_session, ticket, client_user, "Hello")
        types = _types(db_session, ticket, staff=False)
        assert TicketEventType.COMMENT_ADDED in types
        assert TicketEventType.STATUS_CHANGED in types

    def test_comment_and_status_grouped_in_ui(
        self, db_session, project_with_members, client_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        ticket_service.add_comment(db_session, ticket, client_user, "Hello")
        events = event_service.list_ticket_events(db_session, ticket, staff=False)
        rows = event_service.format_ticket_events(db_session, events, lang="en")
        comment_group = next(
            row for row in rows if any("Comment added" in s for s in row.summaries)
        )
        assert any("Status changed" in s for s in comment_group.summaries)
        assert len(comment_group.summaries) >= 2

    def test_participant_and_tag_events(
        self, db_session, project_with_members, staff_user, client_user
    ):
        ticket = make_ticket(db_session, project_with_members, client_user)
        peer = make_user(
            db_session,
            "peer-hist@test.local",
            project=project_with_members,
        )
        ticket_service.add_participant(db_session, ticket, staff_user, peer.id)
        ticket_service.add_ticket_tag(db_session, ticket, staff_user, "alpha")
        ticket = ticket_service.get_ticket(db_session, ticket.id)
        assert ticket is not None
        tag_id = ticket.ticket_tags[0].tag_id
        ticket_service.remove_ticket_tag(db_session, ticket, staff_user, tag_id)
        ticket_service.remove_participant(db_session, ticket, peer)
        types = _types(db_session, ticket, staff=True)
        assert TicketEventType.PARTICIPANT_ADDED in types
        assert TicketEventType.PARTICIPANT_REMOVED in types
        assert TicketEventType.TAG_ADDED in types
        assert TicketEventType.TAG_REMOVED in types
