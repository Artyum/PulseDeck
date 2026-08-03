from datetime import datetime, timedelta, timezone

from app.models.enums import MagicTokenPurpose, TicketType
from app.services import reply_token as reply_token_service
from app.services import tickets as ticket_service
from app.services.auth import hash_magic_token
from app.services.reply_token import ReplyTokenStatus


class TestReplyToken:
    def test_create_two_tokens_both_valid(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="T",
            description="D",
            ticket_type=TicketType.BUG,
        )
        raw1 = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        raw2 = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        assert reply_token_service.resolve_reply_token(db_session, raw1) is not None
        assert reply_token_service.resolve_reply_token(db_session, raw2) is not None
        assert raw1 != raw2

    def test_classify_used_and_expired(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="T2",
            description="D",
            ticket_type=TicketType.BUG,
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        row = reply_token_service.lookup_reply_token(db_session, raw)
        assert row is not None
        assert reply_token_service.classify_reply_token(row) == ReplyTokenStatus.OK

        row.used_at = datetime.now(timezone.utc)
        db_session.commit()
        assert (
            reply_token_service.classify_reply_token(
                reply_token_service.lookup_reply_token(db_session, raw)
            )
            == ReplyTokenStatus.USED
        )

        raw2 = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        row2 = reply_token_service.lookup_reply_token(db_session, raw2)
        assert row2 is not None
        row2.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
        assert (
            reply_token_service.classify_reply_token(
                reply_token_service.lookup_reply_token(db_session, raw2)
            )
            == ReplyTokenStatus.EXPIRED
        )

    def test_purpose_is_ticket_reply(
        self, db_session, project_with_members, client_user, staff_user
    ):
        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=client_user,
            title="T3",
            description="D",
            ticket_type=TicketType.BUG,
        )
        raw = reply_token_service.create_reply_token(db_session, staff_user, ticket)
        row = reply_token_service.lookup_reply_token(db_session, raw)
        assert row is not None
        assert row.purpose == MagicTokenPurpose.TICKET_REPLY.value
        assert row.ticket_id == ticket.id
        assert row.token == hash_magic_token(raw)
        assert row.used_at is None
