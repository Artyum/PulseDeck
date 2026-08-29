import pytest
from fastapi import HTTPException

from app.models.enums import UserRole
from app.services import projects as project_service
from tests.helpers import make_user


class TestListProjects:
    def test_active_only(self, db_session, project_with_members, staff_user):
        project_service.set_project_active(
            db_session, project_with_members, active=False
        )
        active = project_service.create_project(
            db_session, "Active", "ACTV", initial_staff_ids=[staff_user.id]
        )
        rows = project_service.list_projects(db_session, active_only=True)
        keys = {p.key for p in rows}
        assert active.key in keys
        assert project_with_members.key not in keys

    def test_list_project_summaries_empty(self, db_session):
        assert project_service.list_project_summaries(db_session) == []

    def test_list_project_summaries(
        self, db_session, project_with_members, client_user
    ):
        summaries = project_service.list_project_summaries(db_session)
        assert len(summaries) >= 1
        demo = next(s for s in summaries if s.project.id == project_with_members.id)
        assert demo.member_count >= 1

    def test_list_user_projects_admin_sees_active_only(
        self, db_session, admin_user, project_with_members
    ):
        project_service.set_project_active(
            db_session, project_with_members, active=False
        )
        rows = project_service.list_user_projects(db_session, admin_user)
        assert all(p.is_active for p in rows)

    def test_list_user_projects_member(
        self, db_session, client_user, project_with_members
    ):
        rows = project_service.list_user_projects(db_session, client_user)
        assert any(p.id == project_with_members.id for p in rows)


class TestProjectCrud:
    def test_update_project(self, db_session, project_with_members):
        updated = project_service.update_project(
            db_session,
            project_with_members,
            name="Renamed",
            key=project_with_members.key,
            description="New desc",
        )
        assert updated.name == "Renamed"
        assert updated.description == "New desc"

    def test_update_project_notify_clients_on_staff_ticket(
        self, db_session, project_with_members
    ):
        updated = project_service.update_project(
            db_session,
            project_with_members,
            name=project_with_members.name,
            key=project_with_members.key,
            notify_clients_on_staff_ticket=True,
        )
        assert updated.notify_clients_on_staff_ticket is True
        updated = project_service.update_project(
            db_session,
            updated,
            name=updated.name,
            key=updated.key,
            notify_clients_on_staff_ticket=False,
        )
        assert updated.notify_clients_on_staff_ticket is False

    def test_list_project_clients(self, db_session, project_with_members, client_user):
        other_client = make_user(
            db_session,
            "client2@test.local",
            role=UserRole.USER,
            project=project_with_members,
        )
        clients = project_service.list_project_clients(
            db_session, project_with_members.id
        )
        emails = {user.email.lower() for user in clients}
        assert client_user.email.lower() in emails
        assert other_client.email.lower() in emails

    def test_update_duplicate_name(self, db_session, project_with_members, staff_user):
        other = project_service.create_project(
            db_session, "Other", "OTHR", initial_staff_ids=[staff_user.id]
        )
        with pytest.raises(ValueError):
            project_service.update_project(
                db_session,
                other,
                name=project_with_members.name,
                key="OTHR2",
            )

    def test_create_requires_staff(self, db_session):
        with pytest.raises(ValueError):
            project_service.create_project(db_session, "NoStaff", "NSTF")

    def test_create_empty_name(self, db_session, staff_user):
        with pytest.raises(ValueError):
            project_service.create_project(
                db_session, "  ", "KEY1", initial_staff_ids=[staff_user.id]
            )

    def test_get_project_by_key_or_404_inactive(self, db_session, project_with_members):
        project_service.set_project_active(
            db_session, project_with_members, active=False
        )
        with pytest.raises(HTTPException) as exc:
            project_service.get_project_by_key_or_404(
                db_session, project_with_members.key, require_active=True
            )
        assert exc.value.status_code == 404

    def test_get_project_by_key_or_404_missing(self, db_session):
        with pytest.raises(HTTPException):
            project_service.get_project_by_key_or_404(db_session, "ZZZZZ")


class TestHasStaffCapabilities:
    def test_admin_without_membership(
        self, db_session, admin_user, project_with_members
    ):
        assert (
            project_service.has_staff_capabilities(
                db_session, project_with_members.id, admin_user
            )
            is True
        )

    def test_client_member_false(self, db_session, client_user, project_with_members):
        assert (
            project_service.has_staff_capabilities(
                db_session, project_with_members.id, client_user
            )
            is False
        )


class TestMembership:
    def test_add_admin_as_member(self, db_session, admin_user, project_with_members):
        project_service.add_project_member(
            db_session, project_with_members.id, admin_user.id
        )
        assert project_service.is_project_member(
            db_session, project_with_members.id, admin_user.id
        )
        assert project_service.is_project_staff(
            db_session, project_with_members.id, admin_user
        )

    def test_admin_without_membership_not_staff(
        self, db_session, admin_user, project_with_members
    ):
        assert not project_service.is_project_member(
            db_session, project_with_members.id, admin_user.id
        )
        assert not project_service.is_project_staff(
            db_session, project_with_members.id, admin_user
        )

    def test_remove_last_staff_fails(
        self, db_session, project_with_members, staff_user
    ):
        with pytest.raises(ValueError):
            project_service.remove_project_member(
                db_session, project_with_members.id, staff_user.id
            )

    def test_is_project_member_false_for_non_member(self, db_session, admin_user):
        assert (
            project_service.is_project_member(db_session, 999999, admin_user.id)
            is False
        )


class TestSetUserProjects:
    def test_set_projects(
        self, db_session, client_user, project_with_members, staff_user
    ):
        other = project_service.create_project(
            db_session, "Second", "SEC2", initial_staff_ids=[staff_user.id]
        )
        project_service.set_user_projects(db_session, client_user.id, [other.id])
        rows = project_service.list_user_projects(db_session, client_user)
        assert {p.id for p in rows} == {other.id}
