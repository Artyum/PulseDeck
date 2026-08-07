from app.services import tickets as ticket_service
from app.utils.unwatch import (
    make_unwatch_token,
    make_unwatch_url,
    parse_unwatch_token,
)
from tests.helpers import peer_participant_ticket


class TestUnwatchToken:
    def test_round_trip(self):
        token = make_unwatch_token(42, 7)
        assert parse_unwatch_token(token) == (42, 7)

    def test_rejects_bad_input(self):
        token = make_unwatch_token(1, 2)
        assert parse_unwatch_token(token[:-4] + "abcd") is None
        assert parse_unwatch_token("") is None
        assert parse_unwatch_token("1.2") is None

    def test_make_url(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("APP_BASE_URL", "https://pulsedeck.example")
        get_settings.cache_clear()
        try:
            url = make_unwatch_url(7, 12)
            assert url.startswith("https://pulsedeck.example/email/unwatch?token=")
            assert parse_unwatch_token(url.rsplit("token=", 1)[-1]) == (7, 12)
        finally:
            get_settings.cache_clear()


class TestUnwatchTicket:
    def test_is_ticket_watcher(self, db_session, project_with_members, client_user):
        ticket, peer = peer_participant_ticket(
            db_session, project_with_members, client_user, notify_reply=False
        )
        assert ticket_service.is_ticket_watcher(ticket, peer.id) is True
        assert ticket_service.is_ticket_watcher(ticket, client_user.id) is False

    def test_unwatch_removes_participant(
        self, db_session, project_with_members, client_user
    ):
        from sqlalchemy import select

        from app.models.ticket import TicketParticipant

        ticket, peer = peer_participant_ticket(
            db_session, project_with_members, client_user, notify_reply=False
        )
        assert ticket_service.unwatch_ticket(db_session, peer.id, ticket.id) is True
        row = db_session.scalar(
            select(TicketParticipant).where(
                TicketParticipant.ticket_id == ticket.id,
                TicketParticipant.user_id == peer.id,
            )
        )
        assert row is None

    def test_unwatch_idempotent(self, db_session, project_with_members, client_user):
        ticket, peer = peer_participant_ticket(
            db_session, project_with_members, client_user, notify_reply=False
        )
        assert ticket_service.unwatch_ticket(db_session, peer.id, ticket.id) is True
        assert ticket_service.unwatch_ticket(db_session, peer.id, ticket.id) is True
