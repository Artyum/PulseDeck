from sqlalchemy import select

from app.models.ticket import TicketParticipant
from app.utils.unwatch import make_unwatch_token
from tests.helpers import peer_participant_ticket


class TestUnwatchRoutes:
    def test_get_shows_confirmation_without_removing_participant(
        self, client, db_session, project_with_members, client_user
    ):
        ticket, peer = peer_participant_ticket(
            db_session, project_with_members, client_user, notify_reply=False
        )
        token = make_unwatch_token(peer.id, ticket.id)

        response = client.get("/email/unwatch", params={"token": token})

        row = db_session.scalar(
            select(TicketParticipant).where(
                TicketParticipant.ticket_id == ticket.id,
                TicketParticipant.user_id == peer.id,
            )
        )
        assert response.status_code == 200
        assert 'name="token"' in response.text
        assert row is not None

    def test_form_post_unwatches_and_returns_html(
        self, client, db_session, project_with_members, client_user
    ):
        ticket, peer = peer_participant_ticket(
            db_session, project_with_members, client_user, notify_reply=False
        )
        token = make_unwatch_token(peer.id, ticket.id)

        response = client.post("/email/unwatch", data={"token": token})

        row = db_session.scalar(
            select(TicketParticipant).where(
                TicketParticipant.ticket_id == ticket.id,
                TicketParticipant.user_id == peer.id,
            )
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert row is None
