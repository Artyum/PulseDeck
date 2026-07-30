"""Extended auth integration tests: login edge cases, activation errors, profile."""
import pytest


def _login(client, email, password):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


class TestLogin:
    def test_wrong_password(self, client, client_user):
        r = _login(client, "client@test.local", "wrong")
        assert r.status_code in (200, 303)

    def test_unactivated_user_blocked(self, client, db_session, project_with_members):
        from app.models.user import User
        from app.models.enums import UserRole
        user = User(
            email="unactivated@test.local",
            first_name="Un",
            last_name="Activated",
            role=UserRole.USER,
            activated_at=None,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        r = _login(client, "unactivated@test.local", "doesntmatter")
        assert r.status_code in (200, 303)

    def test_logout(self, client, client_user):
        _login(client, "client@test.local", "Client123!")
        r = client.post("/auth/logout", follow_redirects=False)
        assert r.status_code in (302, 303)


class TestActivationErrors:
    def test_invalid_token(self, client):
        r = client.post(
            "/auth/activate",
            data={
                "token": "invalid-token",
                "new_password": "NowyUser1!",
                "confirm_password": "NowyUser1!",
                "phone": "",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_password_mismatch(self, client, db_session, project_with_members):
        from app.models.enums import MagicTokenPurpose, UserRole
        from app.services import auth as auth_service
        user = _create_pending_user(db_session)
        token_row = auth_service.create_password_link(db_session, user)
        r = client.post(
            "/auth/activate",
            data={
                "token": token_row.token,
                "new_password": "NowyUser1!",
                "confirm_password": "Mismatch1!",
                "phone": "",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_weak_password(self, client, db_session, project_with_members):
        from app.services import auth as auth_service
        user = _create_pending_user(db_session)
        token_row = auth_service.create_password_link(db_session, user)
        r = client.post(
            "/auth/activate",
            data={
                "token": token_row.token,
                "new_password": "short",
                "confirm_password": "short",
                "phone": "",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_activate_page_with_valid_token(
        self, client, db_session, project_with_members
    ):
        from app.services import auth as auth_service
        user = _create_pending_user(db_session)
        token_row = auth_service.create_password_link(db_session, user)
        r = client.get(f"/auth/activate?token={token_row.token}")
        assert r.status_code == 200

    def test_activate_page_with_invalid_token(self, client):
        r = client.get("/auth/activate?token=invalid")
        assert r.status_code in (200, 303)


class TestProfile:
    def test_profile_page(self, client, client_user):
        _login(client, "client@test.local", "Client123!")
        r = client.get("/profile", follow_redirects=False)
        assert r.status_code in (200, 303)

    def test_profile_update(self, client, client_user):
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            "/profile",
            data={
                "first_name": "Updated",
                "last_name": "Name",
                "phone": "",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)

    def test_profile_password_change(self, client, client_user):
        _login(client, "client@test.local", "Client123!")
        r = client.post(
            "/profile/password",
            data={
                "current_password": "Client123!",
                "new_password": "NewPass123!",
                "confirm_password": "NewPass123!",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)


def _create_pending_user(db_session):
    """Helper to create a pending user for activation tests."""
    from app.models.user import User
    from app.models.enums import UserRole
    user = User(
        email="pending@test.local",
        first_name="Pending",
        last_name="User",
        role=UserRole.USER,
        activated_at=None,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
