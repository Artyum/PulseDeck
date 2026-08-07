from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.enums import TicketPriority, TicketStatus, TicketType, UserRole
from app.services import tickets as ticket_service
from tests.helpers import make_ticket, make_user, peer_participant_ticket


class TestListTicketsFilters:
    def test_view_open_and_mine_client(
        self, db_session, project_with_members, client_user, staff_user
    ):
        mine = make_ticket(db_session, project_with_members, client_user, title="Mine")
        other = make_ticket(db_session, project_with_members, staff_user, title="Other")
        open_rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            view="open",
        )
        open_ids = {t.id for t in open_rows.items}
        assert mine.id in open_ids
        assert other.id in open_ids
        mine_rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            view="open",
            mine=True,
        )
        mine_ids = {t.id for t in mine_rows.items}
        assert mine.id in mine_ids
        assert other.id not in mine_ids

    def test_staff_view_unassigned(self, db_session, project_with_members, staff_user):
        t = make_ticket(
            db_session, project_with_members, staff_user, title="Unassigned"
        )
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="unassigned",
        )
        assert any(r.id == t.id for r in rows.items)
        ticket_service.assign_ticket(db_session, t, staff_user, staff_user.id)
        rows_after = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="unassigned",
        )
        assert all(r.id != t.id for r in rows_after.items)

    def test_staff_mine_includes_author_assignee_and_participant(
        self, db_session, project_with_members, staff_user, client_user
    ):
        authored = make_ticket(
            db_session, project_with_members, staff_user, title="Authored"
        )
        assigned = make_ticket(
            db_session, project_with_members, client_user, title="Assigned"
        )
        ticket_service.assign_ticket(db_session, assigned, staff_user, staff_user.id)
        watched = make_ticket(
            db_session, project_with_members, client_user, title="Watched"
        )
        ticket_service.add_participant(db_session, watched, staff_user, staff_user.id)
        other = make_ticket(
            db_session, project_with_members, client_user, title="Other"
        )
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="all",
            mine=True,
        )
        ids = {t.id for t in rows.items}
        assert authored.id in ids
        assert assigned.id in ids
        assert watched.id in ids
        assert other.id not in ids

    def test_priority_and_type_filters(
        self, db_session, project_with_members, client_user
    ):
        high = make_ticket(
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
            view="open",
            priority_filter="HIGH",
            type_filter="BUG",
            sort="priority",
        )
        assert any(r.id == high.id for r in rows.items)

    def test_status_filter(self, db_session, project_with_members, client_user):
        done = make_ticket(
            db_session, project_with_members, client_user, title="Done one"
        )
        done.status = TicketStatus.DONE
        open_one = make_ticket(
            db_session, project_with_members, client_user, title="Open one"
        )
        db_session.commit()
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            view="all",
            status_filter="DONE",
        )
        ids = {r.id for r in rows.items}
        assert done.id in ids
        assert open_one.id not in ids

    def test_view_status_filters_exclusive(
        self, db_session, project_with_members, client_user
    ):
        waiting = make_ticket(
            db_session, project_with_members, client_user, title="Waiting one"
        )
        waiting.status = TicketStatus.WAITING_ON_CLIENT
        done = make_ticket(
            db_session, project_with_members, client_user, title="Done one"
        )
        done.status = TicketStatus.DONE
        db_session.commit()
        by_view = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            view="done",
            status_filter="WAITING_ON_CLIENT",
        )
        by_view_ids = {r.id for r in by_view.items}
        assert waiting.id in by_view_ids
        assert done.id not in by_view_ids
        by_status = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            view="open",
            status_filter="DONE",
        )
        by_status_ids = {r.id for r in by_status.items}
        assert done.id in by_status_ids
        assert waiting.id not in by_status_ids

    def test_invalid_filters_ignored(
        self, db_session, project_with_members, client_user
    ):
        make_ticket(db_session, project_with_members, client_user)
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            priority_filter="NOPE",
            type_filter="NOPE",
            status_filter="NOPE",
            sort="created_at",
        )
        assert len(rows.items) >= 1

    def test_search_by_title_and_number(
        self, db_session, project_with_members, client_user
    ):
        t = make_ticket(
            db_session, project_with_members, client_user, title="UniqueNeedle"
        )
        by_title = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            q="UniqueNeedle",
        )
        assert any(r.id == t.id for r in by_title.items)
        by_num = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=client_user,
            q=f"{project_with_members.key}-{t.number}",
        )
        assert any(r.id == t.id for r in by_num.items)

    def test_search_by_author_name(
        self, db_session, project_with_members, client_user, staff_user
    ):
        t = make_ticket(db_session, project_with_members, client_user, title="ByAuthor")
        by_first = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            q=client_user.first_name,
        )
        assert any(r.id == t.id for r in by_first.items)
        by_last = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            q=client_user.last_name,
        )
        assert any(r.id == t.id for r in by_last.items)
        by_full = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            q=f"{client_user.first_name} {client_user.last_name}",
        )
        assert any(r.id == t.id for r in by_full.items)

    def test_search_ignores_view_when_q_set(
        self, db_session, project_with_members, staff_user
    ):
        t = make_ticket(
            db_session, project_with_members, staff_user, title="OpenNeedle"
        )
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="done",
            q="OpenNeedle",
        )
        assert any(r.id == t.id for r in rows.items)

    def test_filter_by_tag(self, db_session, project_with_members, staff_user):
        t = make_ticket(db_session, project_with_members, staff_user)
        ticket_service.add_ticket_tag(db_session, t, staff_user, "alpha")
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            tag="alpha",
        )
        assert any(r.id == t.id for r in rows.items)

    def test_staff_views(self, db_session, project_with_members, staff_user):
        t = make_ticket(db_session, project_with_members, staff_user)
        ticket_service.assign_ticket(db_session, t, staff_user, staff_user.id)
        for view in (
            "all",
            "needs_us",
            "unassigned",
            "open",
            "done",
        ):
            rows = ticket_service.list_tickets(
                db_session,
                project_with_members.id,
                user=staff_user,
                view=view,
            )
            assert isinstance(rows, ticket_service.TicketListResult)

    def test_client_waiting_and_done_views(
        self, db_session, project_with_members, client_user
    ):
        t = make_ticket(db_session, project_with_members, client_user)
        ticket_service.set_status(db_session, t, client_user, TicketStatus.DONE)
        for view in ("all", "open", "waiting_on_me", "done"):
            rows = ticket_service.list_tickets(
                db_session,
                project_with_members.id,
                user=client_user,
                view=view,
            )
            assert isinstance(rows, ticket_service.TicketListResult)

    def test_client_mine_includes_participant(
        self, db_session, project_with_members, client_user
    ):
        t, peer = peer_participant_ticket(
            db_session, project_with_members, client_user, notify_reply=False
        )
        rows = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=peer,
            view="open",
            mine=True,
        )
        assert any(r.id == t.id for r in rows.items)


class TestListTicketsPagination:
    def test_page_size_and_total(self, db_session, project_with_members, staff_user):
        for i in range(30):
            make_ticket(db_session, project_with_members, staff_user, title=f"T{i}")
        result = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="all",
            page=2,
            page_size=10,
        )
        assert result.total == 30
        assert result.page == 2
        assert result.page_size == 10
        assert len(result.items) == 10
        assert result.last_page == 3
        assert result.has_prev
        assert result.has_next
        assert result.range_start == 11
        assert result.range_end == 20

    def test_empty_total_last_page_and_range(
        self, db_session, project_with_members, staff_user
    ):
        result = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="all",
        )
        assert result.total == 0
        assert result.last_page == 1
        assert result.range_start == 0
        assert result.range_end == 0
        assert not result.has_prev
        assert not result.has_next

    def test_clamp_high_page(self, db_session, project_with_members, staff_user):
        for i in range(5):
            make_ticket(db_session, project_with_members, staff_user, title=f"C{i}")
        result = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="all",
            page=99,
            page_size=10,
        )
        assert result.page == 1
        assert len(result.items) == 5

    def test_count_matches_items_with_tag_and_mine(
        self, db_session, project_with_members, staff_user, client_user
    ):
        mine = make_ticket(
            db_session, project_with_members, staff_user, title="Mine tag"
        )
        other = make_ticket(
            db_session, project_with_members, client_user, title="Other tag"
        )
        ticket_service.add_ticket_tag(db_session, mine, staff_user, "pager")
        ticket_service.add_ticket_tag(db_session, other, staff_user, "pager")
        result = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            mine=True,
            tag="pager",
            page_size=10,
        )
        assert result.total == 1
        assert len(result.items) == result.total

    def test_shrink_dataset_clamps_page(
        self, db_session, project_with_members, staff_user
    ):
        tickets = [
            make_ticket(db_session, project_with_members, staff_user, title=f"S{i}")
            for i in range(100)
        ]
        first = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="all",
            page=4,
            page_size=25,
        )
        assert first.page == 4
        assert len(first.items) == 25
        for t in tickets[:80]:
            db_session.delete(t)
        db_session.commit()
        second = ticket_service.list_tickets(
            db_session,
            project_with_members.id,
            user=staff_user,
            view="all",
            page=4,
            page_size=25,
        )
        assert second.total == 20
        assert second.page == 1
        assert len(second.items) == 20

    def test_normalize_feed_page_size(self):
        assert ticket_service.normalize_feed_page_size(None) == 25
        assert ticket_service.normalize_feed_page_size(50) == 50
        assert ticket_service.normalize_feed_page_size(99) == 25
        assert ticket_service.normalize_feed_page_size("10") == 10


class TestTicketMutations:
    def test_reopen(self, db_session, project_with_members, staff_user):
        t = make_ticket(db_session, project_with_members, staff_user)
        ticket_service.set_status(db_session, t, staff_user, TicketStatus.DONE)
        reopened = ticket_service.reopen_ticket(db_session, t, staff_user)
        assert reopened.status == TicketStatus.IN_PROGRESS
        assert reopened.closed_at is None

    def test_reopen_forbidden_for_client_after_deadline(
        self, db_session, project_with_members, client_user, monkeypatch
    ):
        from dataclasses import replace

        from app.services.portal_settings import get_portal_settings

        t = make_ticket(db_session, project_with_members, client_user)
        ticket_service.set_status(db_session, t, client_user, TicketStatus.DONE)
        t.closed_at = datetime.now(timezone.utc) - timedelta(days=30)
        db_session.commit()
        portal = get_portal_settings(db_session)
        monkeypatch.setattr(
            ticket_service,
            "get_portal_settings",
            lambda _db=None: replace(portal, ticket_reopen_days=7),
        )
        with pytest.raises(HTTPException) as exc:
            ticket_service.reopen_ticket(db_session, t, client_user)
        assert exc.value.status_code == 403

    def test_change_reporter(
        self, db_session, project_with_members, staff_user, client_user
    ):
        t = make_ticket(db_session, project_with_members, staff_user)
        updated = ticket_service.change_reporter(
            db_session, t, staff_user, client_user.id
        )
        assert updated.author_id == client_user.id

    def test_change_reporter_same_noop(
        self, db_session, project_with_members, staff_user
    ):
        t = make_ticket(db_session, project_with_members, staff_user)
        updated = ticket_service.change_reporter(
            db_session, t, staff_user, staff_user.id
        )
        assert updated.author_id == staff_user.id

    def test_assign_and_unassign(self, db_session, project_with_members, staff_user):
        t = make_ticket(db_session, project_with_members, staff_user)
        assigned = ticket_service.assign_ticket(
            db_session, t, staff_user, staff_user.id
        )
        assert assigned.assignee_id == staff_user.id
        assert assigned.status == TicketStatus.IN_PROGRESS
        assert all(p.user_id != staff_user.id for p in assigned.participants)
        cleared = ticket_service.assign_ticket(db_session, assigned, staff_user, None)
        assert cleared.assignee_id is None

    def test_assign_drops_existing_participant_row(
        self, db_session, project_with_members, client_user, staff_user
    ):
        t = make_ticket(db_session, project_with_members, client_user)
        ticket_service.add_participant(db_session, t, staff_user, staff_user.id)
        assigned = ticket_service.assign_ticket(
            db_session, t, staff_user, staff_user.id
        )
        assert assigned.assignee_id == staff_user.id
        assert all(p.user_id != staff_user.id for p in assigned.participants)

    def test_assign_client_rejected(
        self, db_session, project_with_members, staff_user, client_user
    ):
        t = make_ticket(db_session, project_with_members, staff_user)
        with pytest.raises(HTTPException) as exc:
            ticket_service.assign_ticket(db_session, t, staff_user, client_user.id)
        assert exc.value.status_code == 400

    def test_add_and_remove_tag(self, db_session, project_with_members, staff_user):
        t = make_ticket(db_session, project_with_members, staff_user)
        tagged = ticket_service.add_ticket_tag(db_session, t, staff_user, "beta")
        tag_id = tagged.ticket_tags[0].tag_id
        cleared = ticket_service.remove_ticket_tag(
            db_session, tagged, staff_user, tag_id
        )
        assert cleared.ticket_tags == [] or len(cleared.ticket_tags) == 0

    def test_empty_tag_rejected(self, db_session, project_with_members, staff_user):
        t = make_ticket(db_session, project_with_members, staff_user)
        with pytest.raises(HTTPException) as exc:
            ticket_service.add_ticket_tag(db_session, t, staff_user, "   ")
        assert exc.value.status_code == 400

    def test_staff_comment_auto_assign_not_participant(
        self, db_session, project_with_members, client_user, staff_user
    ):
        t = make_ticket(db_session, project_with_members, client_user)
        ticket_service.add_comment(
            db_session,
            t,
            staff_user,
            "Staff reply",
        )
        refreshed = ticket_service.get_ticket(db_session, t.id)
        assert refreshed is not None
        assert refreshed.assignee_id == staff_user.id
        assert all(p.user_id != staff_user.id for p in refreshed.participants)

    def test_staff_comment_becomes_participant_when_not_assignee(
        self, db_session, project_with_members, client_user, staff_user
    ):
        other_staff = make_user(
            db_session,
            "staff-other@test.local",
            first_name="Other",
            last_name="Staff",
            role=UserRole.STAFF,
            project=project_with_members,
        )

        t = make_ticket(db_session, project_with_members, client_user)
        ticket_service.assign_ticket(db_session, t, staff_user, staff_user.id)
        ticket_service.add_comment(
            db_session,
            t,
            other_staff,
            "Another staff reply",
        )
        refreshed = ticket_service.get_ticket(db_session, t.id)
        assert refreshed is not None
        assert any(p.user_id == other_staff.id for p in refreshed.participants)

    def test_add_participant_client_adds_client(
        self, db_session, project_with_members, client_user
    ):
        peer = make_user(
            db_session,
            "peer-add@test.local",
            first_name="Peer",
            last_name="Add",
            password="Peer1234!abcd",
            project=project_with_members,
        )

        t = make_ticket(db_session, project_with_members, client_user)
        updated = ticket_service.add_participant(db_session, t, client_user, peer.id)
        assert any(p.user_id == peer.id for p in updated.participants)

    def test_add_participant_client_cannot_add_staff(
        self, db_session, project_with_members, client_user, staff_user
    ):
        t = make_ticket(db_session, project_with_members, client_user)
        with pytest.raises(HTTPException) as exc:
            ticket_service.add_participant(db_session, t, client_user, staff_user.id)
        assert exc.value.status_code == 400

    def test_add_participant_staff_can_add_staff(
        self, db_session, project_with_members, client_user, staff_user
    ):
        t = make_ticket(db_session, project_with_members, client_user)
        updated = ticket_service.add_participant(
            db_session, t, staff_user, staff_user.id
        )
        assert any(p.user_id == staff_user.id for p in updated.participants)

    def test_add_participant_admin_project_member_can_add_client(
        self, db_session, project_with_members, client_user, admin_user
    ):
        from app.services import projects as project_service

        peer = make_user(
            db_session,
            "peer-admin-add@test.local",
            first_name="Peer",
            last_name="AdminAdd",
            password="Peer1234!abcd",
            project=project_with_members,
        )
        project_service.add_project_member(
            db_session, project_with_members.id, admin_user.id
        )

        t = make_ticket(db_session, project_with_members, client_user)
        updated = ticket_service.add_participant(db_session, t, admin_user, peer.id)
        assert any(p.user_id == peer.id for p in updated.participants)

    def test_add_participant_admin_without_project_membership_forbidden(
        self, db_session, project_with_members, client_user, admin_user
    ):
        peer = make_user(
            db_session,
            "peer-admin-block@test.local",
            first_name="Peer",
            last_name="Block",
            password="Peer1234!abcd",
            project=project_with_members,
        )

        t = make_ticket(db_session, project_with_members, client_user)
        with pytest.raises(HTTPException) as exc:
            ticket_service.add_participant(db_session, t, admin_user, peer.id)
        assert exc.value.status_code == 403

    def test_remove_participant_permissions(
        self, db_session, project_with_members, client_user, staff_user, admin_user
    ):
        t, peer = peer_participant_ticket(
            db_session, project_with_members, client_user, notify_reply=False
        )

        with pytest.raises(HTTPException) as exc:
            ticket_service.remove_participant(db_session, t, client_user, peer.id)
        assert exc.value.status_code == 403

        with pytest.raises(HTTPException) as exc:
            ticket_service.remove_participant(db_session, t, staff_user, peer.id)
        assert exc.value.status_code == 403

        updated = ticket_service.remove_participant(db_session, t, peer, peer.id)
        assert all(p.user_id != peer.id for p in updated.participants)

        ticket_service.add_participant(db_session, updated, client_user, peer.id)
        t = ticket_service.get_ticket(db_session, updated.id)
        assert t is not None
        cleared = ticket_service.remove_participant(db_session, t, admin_user, peer.id)
        assert all(p.user_id != peer.id for p in cleared.participants)

    def test_add_attachment_and_remove(
        self, db_session, project_with_members, client_user
    ):
        t = make_ticket(db_session, project_with_members, client_user)
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
        outsider = make_user(
            db_session,
            "out@test.local",
            first_name="Out",
            last_name="Sider",
            password="Outsider1!abc",
        )
        with pytest.raises(HTTPException) as exc:
            ticket_service.require_project_access(
                db_session, outsider, project_with_members.id
            )
        assert exc.value.status_code == 403

    def test_set_type_same_noop(self, db_session, project_with_members, staff_user):
        t = make_ticket(db_session, project_with_members, staff_user)
        same = ticket_service.set_type(db_session, t, staff_user, TicketType.BUG)
        assert same.type == TicketType.BUG

    def test_client_cannot_set_arbitrary_status(
        self, db_session, project_with_members, client_user
    ):
        t = make_ticket(db_session, project_with_members, client_user)
        with pytest.raises(HTTPException) as exc:
            ticket_service.set_status(
                db_session, t, client_user, TicketStatus.IN_PROGRESS
            )
        assert exc.value.status_code == 403
