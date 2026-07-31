from unittest.mock import patch

import pytest

from app.config import get_settings
from app.models.enums import MagicTokenPurpose, UserRole
from app.models.user import User
from app.services import auth as auth_service
from app.services import projects as project_service


def _pending(db, email="pending@test.local"):
    user = User(
        email=email,
        first_name="Pending",
        last_name="User",
        role=UserRole.USER,
        activated_at=None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestAuthBasics:
    def test_normalize_email(self):
        assert auth_service.normalize_email("  A@B.C  ") == "a@b.c"

    def test_authenticate_wrong_password(self, db_session, client_user):
        assert (
            auth_service.authenticate_password(db_session, "client@test.local", "wrong")
            is None
        )

    def test_authenticate_ok(self, db_session, client_user):
        user = auth_service.authenticate_password(
            db_session, "client@test.local", "Client123!"
        )
        assert user is not None
        assert user.id == client_user.id

    def test_login_blocked_inactive(self, db_session, client_user):
        client_user.is_active = False
        db_session.commit()
        reason = auth_service.login_blocked_reason(client_user)
        assert reason

    def test_login_blocked_unactivated(self, db_session):
        user = _pending(db_session)
        reason = auth_service.login_blocked_reason(user)
        assert reason

    def test_email_taken(self, db_session, client_user):
        assert auth_service.email_taken(db_session, "client@test.local") is True
        assert (
            auth_service.email_taken(
                db_session, "client@test.local", exclude_user_id=client_user.id
            )
            is False
        )


class TestSetActiveAndRole:
    def test_set_active_blocks(self, db_session, admin_user, client_user):
        auth_service.set_active(db_session, client_user, actor=admin_user, active=False)
        assert client_user.is_active is False

    def test_cannot_block_self(self, db_session, admin_user):
        with pytest.raises(ValueError):
            auth_service.set_active(
                db_session, admin_user, actor=admin_user, active=False
            )

    def test_promote_to_admin_clears_memberships(
        self, db_session, admin_user, client_user, project_with_members
    ):
        assert project_service.is_project_member(
            db_session, project_with_members.id, client_user.id
        )
        auth_service.set_user_role(db_session, client_user, UserRole.ADMIN)
        assert client_user.role == UserRole.ADMIN
        assert (
            project_service.is_project_member(
                db_session, project_with_members.id, client_user.id
            )
            is True
        )  # admin always member via role

    def test_cannot_demote_last_admin(self, db_session, admin_user):
        with pytest.raises(ValueError):
            auth_service.set_user_role(db_session, admin_user, UserRole.STAFF)


class TestEmailChange:
    def test_request_and_confirm(self, db_session, client_user):
        _row, raw = auth_service.request_email_change(
            db_session, client_user, "new@test.local"
        )
        assert client_user.pending_email == "new@test.local"
        user = auth_service.confirm_email_change(db_session, raw)
        assert user is not None
        assert user.email == "new@test.local"
        assert user.pending_email is None

    def test_request_same_email_rejected(self, db_session, client_user):
        with pytest.raises(ValueError):
            auth_service.request_email_change(
                db_session, client_user, client_user.email
            )

    def test_request_taken_email_rejected(self, db_session, client_user, admin_user):
        with pytest.raises(ValueError):
            auth_service.request_email_change(db_session, client_user, admin_user.email)

    def test_confirm_invalid_token(self, db_session):
        assert auth_service.confirm_email_change(db_session, "nope") is None


class TestPasswordLinkAndComplete:
    def test_create_and_complete(self, db_session):
        user = _pending(db_session)
        _row, raw = auth_service.create_password_link(db_session, user)
        completed = auth_service.complete_password_set(
            db_session, raw, "NowyUser1!", phone=""
        )
        assert completed is not None
        assert completed.activated_at is not None
        assert completed.password_hash

    def test_blocked_user_cannot_receive_link(self, db_session, client_user):
        client_user.is_active = False
        db_session.commit()
        with pytest.raises(ValueError):
            auth_service.create_password_link(db_session, client_user)

    def test_admin_set_password(self, db_session, client_user):
        auth_service.admin_set_password(db_session, client_user, "ResetPass1!")
        user = auth_service.authenticate_password(
            db_session, client_user.email, "ResetPass1!"
        )
        assert user is not None

    def test_admin_set_email(self, db_session, client_user):
        auth_service.admin_set_email(db_session, client_user, "renamed@test.local")
        db_session.commit()
        assert client_user.email == "renamed@test.local"


class TestPendingUserAndSeed:
    def test_create_pending_user(self, db_session, project_with_members):
        user = auth_service.create_pending_user(
            db_session,
            first_name="Nowy",
            last_name="Klient",
            email="nowy@test.local",
            role=UserRole.USER,
            project_ids=[project_with_members.id],
        )
        assert user.activated_at is None
        assert project_service.is_project_member(
            db_session, project_with_members.id, user.id
        )

    def test_create_pending_duplicate_email(self, db_session, client_user):
        with pytest.raises(ValueError):
            auth_service.create_pending_user(
                db_session,
                first_name="X",
                last_name="Y",
                email=client_user.email,
                role=UserRole.USER,
                project_ids=[],
            )

    def test_ensure_admin_seed_creates(self, db_session, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "seed@test.local")
        monkeypatch.setenv("ADMIN_PASSWORD", "SeedPass1!")
        get_settings.cache_clear()
        try:
            auth_service.ensure_admin_seed(db_session)
            user = auth_service.get_user_by_email(db_session, "seed@test.local")
            assert user is not None
            assert user.role == UserRole.ADMIN
        finally:
            get_settings.cache_clear()

    def test_ensure_admin_seed_skips_without_env(self, db_session, monkeypatch):
        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        get_settings.cache_clear()
        try:
            auth_service.ensure_admin_seed(db_session)
            assert auth_service.get_user_by_email(db_session, "") is None
        finally:
            get_settings.cache_clear()


class TestProfileAndPrefs:
    def test_update_profile_fields(self, db_session, client_user):
        auth_service.update_profile_fields(
            db_session,
            client_user,
            first_name="Jan",
            last_name="Nowak",
            phone="",
        )
        db_session.commit()
        assert client_user.first_name == "Jan"
        assert client_user.last_name == "Nowak"

    def test_update_notification_prefs_client(self, db_session, client_user):
        auth_service.update_notification_prefs(
            db_session,
            client_user,
            notify_new_ticket=True,
            notify_reply=False,
            notify_ticket_update=True,
        )
        assert client_user.notify_reply is False

    def test_update_notification_prefs_staff(self, db_session, staff_user):
        auth_service.update_notification_prefs(
            db_session,
            staff_user,
            notify_new_ticket=False,
            notify_reply=True,
            notify_ticket_update=False,
        )
        assert staff_user.notify_new_ticket is False

    def test_peek_magic_token_used(self, db_session, client_user):
        row, raw = auth_service.create_magic_token(
            db_session, client_user, purpose=MagicTokenPurpose.PASSWORD_SET
        )
        row.used = True
        db_session.commit()
        assert (
            auth_service.peek_magic_token(
                db_session, raw, purpose=MagicTokenPurpose.PASSWORD_SET
            )
            is None
        )

    def test_send_password_link_enqueues(self, db_session, client_user):
        with patch("app.services.email.notify_password_set") as notify:
            auth_service.send_password_link(db_session, client_user)
            notify.assert_called_once()
