import pytest
from fastapi import HTTPException

from app.models.enums import UserRole
from app.services import projects as project_service


class TestListProjects:
    def test_active_only(self, db_session, project_with_members):
        project_service.set_project_active(
            db_session, project_with_members, active=False
        )
        active = project_service.create_project(db_session, "Active", "ACTV")
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

    def test_update_duplicate_name(self, db_session, project_with_members):
        other = project_service.create_project(db_session, "Other", "OTHR")
        with pytest.raises(ValueError):
            project_service.update_project(
                db_session,
                other,
                name=project_with_members.name,
                key="OTHR2",
            )

    def test_create_empty_name(self, db_session):
        with pytest.raises(ValueError):
            project_service.create_project(db_session, "  ", "KEY1")

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


class TestMembership:
    def test_add_admin_noop(self, db_session, admin_user, project_with_members):
        project_service.add_project_member(
            db_session, project_with_members.id, admin_user.id
        )
        members = project_service.list_project_member_users(
            db_session, project_with_members, include_admins=False
        )
        assert all(m.id != admin_user.id for m in members)

    def test_remove_admin_noop(self, db_session, admin_user, project_with_members):
        project_service.remove_project_member(
            db_session, project_with_members.id, admin_user.id
        )

    def test_addable_users(
        self, db_session, project_with_members, client_user, admin_user
    ):
        from datetime import datetime, timezone

        from app.models.user import User
        from app.services.auth import set_password

        free = User(
            email="free@test.local",
            first_name="Free",
            last_name="User",
            role=UserRole.USER,
            activated_at=datetime.now(timezone.utc),
        )
        set_password(free, "FreeUser1!abc")
        db_session.add(free)
        db_session.commit()
        db_session.refresh(free)
        addable = project_service.list_addable_users(db_session, project_with_members)
        ids = {u.id for u in addable}
        assert free.id in ids
        assert client_user.id not in ids
        assert admin_user.id not in ids

    def test_set_user_projects(self, db_session, client_user, project_with_members):
        other = project_service.create_project(db_session, "Second", "SEC2")
        project_service.set_user_projects(db_session, client_user.id, [other.id])
        db_session.commit()
        assert project_service.is_project_member(db_session, other.id, client_user.id)
        assert not project_service.is_project_member(
            db_session, project_with_members.id, client_user.id
        )

    def test_set_user_projects_admin_clears(
        self, db_session, admin_user, project_with_members
    ):
        project_service.set_user_projects(db_session, admin_user.id, [])
        db_session.commit()

    def test_resolve_project_ids_empty(self, db_session):
        with pytest.raises(ValueError):
            project_service.resolve_project_ids(db_session, [])

    def test_resolve_project_ids_invalid(self, db_session):
        with pytest.raises(ValueError):
            project_service.resolve_project_ids(db_session, [99999])

    def test_list_project_tags_for_projects_empty(self, db_session):
        assert project_service.list_project_tags_for_projects(db_session, []) == {}
