from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.enums import TicketPriority, TicketStatus, TicketType
from app.services import tickets as ticket_service


def _ticket(db, project, author, **kwargs):
    return ticket_service.create_ticket(
        db,
        project_id=project.id,
        author=author,
        title=kwargs.get("title", "Ticket"),
        description=kwargs.get("description", "Desc"),
        ticket_type=kwargs.get("ticket_type", TicketType.BUG),
        priority=kwargs.get("priority", TicketPriority.NORMAL),
    )


class TestListTicketsFilters:
    def test_view_open_client(self, db_session, project_with_members, client_user):
        open_t = _ticket(db_session, project_with_members, client_user, title="Open")
        done = _ticket(db_session, project_with_members, client_user, title="Done")
        ticket_service.set_status(db_session, done, client_user, TicketStatus.DONE)
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            view="open",
        )
        ids = {t.id for t in rows}
        assert open_t.id in ids
        assert done.id not in ids

    def test_view_mine(self, db_session, project_with_members, client_user, staff_user):
        mine = _ticket(db_session, project_with_members, client_user, title="Mine")
        other = _ticket(db_session, project_with_members, staff_user, title="Other")
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            view="mine",
        )
        ids = {t.id for t in rows}
        assert mine.id in ids
        assert other.id not in ids

    def test_staff_unassigned(self, db_session, project_with_members, staff_user):
        t = _ticket(db_session, project_with_members, staff_user, title="Unassigned")
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="unassigned",
        )
        assert any(r.id == t.id for r in rows)

    def test_status_and_priority_filters(
        self, db_session, project_with_members, client_user
    ):
        high = _ticket(
            db_session,
            project_with_members,
            client_user,
            title="High",
            priority=TicketPriority.HIGH,
        )
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            status_filter="NEW",
            priority_filter="HIGH",
            type_filter="BUG",
            sort="priority",
        )
        assert any(r.id == high.id for r in rows)

    def test_invalid_filters_ignored(
        self, db_session, project_with_members, client_user
    ):
        _ticket(db_session, project_with_members, client_user)
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            status_filter="NOPE",
            priority_filter="NOPE",
            type_filter="NOPE",
            sort="created_at",
        )
        assert len(rows) >= 1

    def test_search_by_title_and_number(
        self, db_session, project_with_members, client_user
    ):
        t = _ticket(db_session, project_with_members, client_user, title="UniqueNeedle")
        by_title = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            q="UniqueNeedle",
        )
        assert any(r.id == t.id for r in by_title)
        by_num = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            q=f"{project_with_members.key}-{t.number}",
        )
        assert any(r.id == t.id for r in by_num)

    def test_filter_by_tag(self, db_session, project_with_members, staff_user):
        t = _ticket(db_session, project_with_members, staff_user)
        ticket_service.add_ticket_tag(db_session, t, staff_user, "alpha")
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            tag="alpha",
        )
        assert any(r.id == t.id for r in rows)

    def test_staff_views(self, db_session, project_with_members, staff_user):
        t = _ticket(db_session, project_with_members, staff_user)
        ticket_service.assign_ticket(db_session, t, staff_user, staff_user.id)
        for view in (
            "mine_open",
            "waiting_on_client",
            "needs_us",
            "done",
            "all",
        ):
            rows = ticket_service.list_tickets(
                db_session,
                project_with_members.id,
                user=staff_user,
                view=view,
            )
            assert isinstance(rows, list)

    def test_client_waiting_and_done_views(
        self, db_session, project_with_members, client_user
    ):
        t = _ticket(db_session, project_with_members, client_user)
        ticket_service.set_status(db_session, t, client_user, TicketStatus.DONE)
        for view in ("waiting_on_me", "done"):
            rows = ticket_service.list_tickets(
                db_session,
                project_with_members.id,
                user=client_user,
                view=view,
            )
            assert isinstance(rows, list)


class TestTicketMutations:
    def test_reopen(self, db_session, project_with_members, staff_user):
        t = _ticket(db_session, project_with_members, staff_user)
        ticket_service.set_status(db_session, t, staff_user, TicketStatus.DONE)
        reopened = ticket_service.reopen_ticket(db_session, t, staff_user)
        assert reopened.status == TicketStatus.IN_PROGRESS
        assert reopened.closed_at is None

    def test_reopen_forbidden_for_client_after_deadline(
        self, db_session, project_with_members, client_user, monkeypatch
    ):
        from app.config import get_settings

        t = _ticket(db_session, project_with_members, client_user)
        ticket_service.set_status(db_session, t, client_user, TicketStatus.DONE)
        t.closed_at = datetime.now(timezone.utc) - timedelta(days=30)
        db_session.commit()
        monkeypatch.setattr(get_settings(), "ticket_reopen_days", 7)
        with pytest.raises(HTTPException) as exc:
            ticket_service.reopen_ticket(db_session, t, client_user)
        assert exc.value.status_code == 403

    def test_change_reporter(
        self, db_session, project_with_members, staff_user, client_user
    ):
        t = _ticket(db_session, project_with_members, staff_user)
        updated = ticket_service.change_reporter(
            db_session, t, staff_user, client_user.id
        )
        assert updated.author_id == client_user.id

    def test_change_reporter_same_noop(
        self, db_session, project_with_members, staff_user
    ):
        t = _ticket(db_session, project_with_members, staff_user)
        updated = ticket_service.change_reporter(
            db_session, t, staff_user, staff_user.id
        )
        assert updated.author_id == staff_user.id

    def test_assign_and_unassign(self, db_session, project_with_members, staff_user):
        t = _ticket(db_session, project_with_members, staff_user)
        assigned = ticket_service.assign_ticket(
            db_session, t, staff_user, staff_user.id
        )
        assert assigned.assignee_id == staff_user.id
        assert assigned.status == TicketStatus.IN_PROGRESS
        cleared = ticket_service.assign_ticket(db_session, assigned, staff_user, None)
        assert cleared.assignee_id is None

    def test_assign_client_rejected(
        self, db_session, project_with_members, staff_user, client_user
    ):
        t = _ticket(db_session, project_with_members, staff_user)
        with pytest.raises(HTTPException) as exc:
            ticket_service.assign_ticket(db_session, t, staff_user, client_user.id)
        assert exc.value.status_code == 400

    def test_add_and_remove_tag(self, db_session, project_with_members, staff_user):
        t = _ticket(db_session, project_with_members, staff_user)
        tagged = ticket_service.add_ticket_tag(db_session, t, staff_user, "beta")
        tag_id = tagged.ticket_tags[0].tag_id
        cleared = ticket_service.remove_ticket_tag(
            db_session, tagged, staff_user, tag_id
        )
        assert cleared.ticket_tags == [] or len(cleared.ticket_tags) == 0

    def test_empty_tag_rejected(self, db_session, project_with_members, staff_user):
        t = _ticket(db_session, project_with_members, staff_user)
        with pytest.raises(HTTPException) as exc:
            ticket_service.add_ticket_tag(db_session, t, staff_user, "   ")
        assert exc.value.status_code == 400

    def test_add_participant(
        self, db_session, project_with_members, client_user, staff_user
    ):
        t = _ticket(db_session, project_with_members, client_user)
        updated = ticket_service.add_participant(
            db_session, t, client_user, staff_user.id
        )
        assert any(p.user_id == staff_user.id for p in updated.participants)

    def test_stop_watching(
        self, db_session, project_with_members, client_user, staff_user
    ):
        from app.models.enums import UserRole
        from app.models.user import User
        from app.services import projects as project_service
        from app.services.auth import set_password

        peer = User(
            email="peer@test.local",
            first_name="Peer",
            last_name="Client",
            role=UserRole.USER,
            activated_at=datetime.now(timezone.utc),
        )
        set_password(peer, "Peer1234!")
        db_session.add(peer)
        db_session.commit()
        db_session.refresh(peer)
        project_service.add_project_member(db_session, project_with_members.id, peer.id)

        t = _ticket(db_session, project_with_members, client_user)
        ticket_service.add_participant(db_session, t, client_user, peer.id)
        t = ticket_service.get_ticket(db_session, t.id)
        updated = ticket_service.remove_self_participant(db_session, t, peer)
        assert all(p.user_id != peer.id for p in updated.participants)

        with pytest.raises(HTTPException) as exc:
            ticket_service.remove_self_participant(db_session, updated, staff_user)
        assert exc.value.status_code == 403

    def test_add_attachment_and_remove(
        self, db_session, project_with_members, client_user
    ):
        t = _ticket(db_session, project_with_members, client_user)
        att = ticket_service.add_attachment(
            db_session,
            file_name="a.jpg",
            file_path="tickets/a.jpg",
            ticket_id=t.id,
        )
        t = ticket_service.get_ticket(db_session, t.id)
        assert t is not None
        cleared = ticket_service.remove_ticket_attachments(
            db_session, t, client_user, [att.id]
        )
        assert all(a.id != att.id for a in cleared.attachments)

    def test_require_project_access_denied(self, db_session, project_with_members):
        from app.models.enums import UserRole
        from app.models.user import User
        from app.services.auth import set_password

        outsider = User(
            email="out@test.local",
            first_name="Out",
            last_name="Sider",
            role=UserRole.USER,
            activated_at=datetime.now(timezone.utc),
        )
        set_password(outsider, "Outsider1!")
        db_session.add(outsider)
        db_session.commit()
        db_session.refresh(outsider)
        with pytest.raises(HTTPException) as exc:
            ticket_service.require_project_access(
                db_session, outsider, project_with_members.id
            )
        assert exc.value.status_code == 403

    def test_set_type_same_noop(self, db_session, project_with_members, client_user):
        t = _ticket(db_session, project_with_members, client_user)
        same = ticket_service.set_type(db_session, t, client_user, TicketType.BUG)
        assert same.type == TicketType.BUG

    def test_client_cannot_set_arbitrary_status(
        self, db_session, project_with_members, client_user
    ):
        t = _ticket(db_session, project_with_members, client_user)
        with pytest.raises(HTTPException) as exc:
            ticket_service.set_status(
                db_session, t, client_user, TicketStatus.IN_PROGRESS
            )
        assert exc.value.status_code == 403
