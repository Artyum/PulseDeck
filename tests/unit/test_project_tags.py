"""Tests for project tag queries (list_used_project_tags)."""

from app.models.ticket import Tag, TicketTag
from app.services import projects as project_service
from tests.helpers import make_ticket


def _create_project(db, staff, name="Test", key="TEST"):
    return project_service.create_project(db, name, key, initial_staff_ids=[staff.id])


def _create_tag(db, project, name):
    tag = Tag(project_id=project.id, name=name)
    db.add(tag)
    db.flush()
    return tag


def _link_tag(db, ticket, tag):
    db.add(TicketTag(ticket_id=ticket.id, tag_id=tag.id))
    db.flush()


class TestListUsedProjectTags:
    def test_used_tags_returns_only_linked(self, db_session, client_user, staff_user):
        project = _create_project(db_session, staff_user)
        project_service.add_project_member(db_session, project.id, client_user.id)
        tag_used = _create_tag(db_session, project, "urgent")
        tag_orphan = _create_tag(db_session, project, "orphan")
        ticket = make_ticket(db_session, project, client_user)
        _link_tag(db_session, ticket, tag_used)
        result = project_service.list_used_project_tags(db_session, project.id)
        assert [t.name for t in result] == ["urgent"]
        assert tag_orphan not in result

    def test_used_tags_empty_when_no_tags(self, db_session, client_user, staff_user):
        project = _create_project(db_session, staff_user)
        project_service.add_project_member(db_session, project.id, client_user.id)
        make_ticket(db_session, project, client_user)
        result = project_service.list_used_project_tags(db_session, project.id)
        assert result == []

    def test_used_tags_empty_when_no_tickets(self, db_session, staff_user):
        project = _create_project(db_session, staff_user)
        _create_tag(db_session, project, "floating")
        result = project_service.list_used_project_tags(db_session, project.id)
        assert result == []

    def test_used_tags_distinct(self, db_session, client_user, staff_user):
        project = _create_project(db_session, staff_user)
        project_service.add_project_member(db_session, project.id, client_user.id)
        tag = _create_tag(db_session, project, "common")
        ticket1 = make_ticket(db_session, project, client_user)
        ticket2 = make_ticket(db_session, project, client_user)
        _link_tag(db_session, ticket1, tag)
        _link_tag(db_session, ticket2, tag)
        result = project_service.list_used_project_tags(db_session, project.id)
        assert len(result) == 1
        assert result[0].name == "common"
