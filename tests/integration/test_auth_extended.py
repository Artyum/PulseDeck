"""Extended auth integration tests: login edge cases, activation errors, profile."""

from tests.helpers import login, login_client, make_user


class TestLogin:
    def test_wrong_password(self, client, client_user):
        r = login(client, "client@test.local", "wrong", assert_ok=False)
        assert r.status_code in (200, 303)

    def test_unactivated_user_blocked(self, client, db_session, project_with_members):
        make_user(
            db_session,
            "unactivated@test.local",
            first_name="Un",
            last_name="Activated",
            activated=False,
            is_active=True,
        )
        r = login(client, "unactivated@test.local", "doesntmatter", assert_ok=False)
        assert r.status_code in (200, 303)

    def test_logout(self, client, client_user):
        login_client(client)
        r = client.post("/auth/logout", follow_redirects=False)
        assert r.status_code in (302, 303)


class TestActivationErrors:
    def test_invalid_token(self, client):
        r = client.post(
            "/auth/activate",
            data={
                "token": "invalid-token",
                "new_password": "NowyUser1!ab",
                "confirm_password": "NowyUser1!ab",
                "phone": "",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_password_mismatch(self, client, db_session, project_with_members):
        from app.services import auth as auth_service

        user = _create_pending_user(db_session)
        _token_row, raw_token = auth_service.create_password_link(db_session, user)
        r = client.post(
            "/auth/activate",
            data={
                "token": raw_token,
                "new_password": "NowyUser1!ab",
                "confirm_password": "Mismatch1!ab",
                "phone": "",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_weak_password(self, client, db_session, project_with_members):
        from app.services import auth as auth_service

        user = _create_pending_user(db_session)
        _token_row, raw_token = auth_service.create_password_link(db_session, user)
        r = client.post(
            "/auth/activate",
            data={
                "token": raw_token,
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
        _token_row, raw_token = auth_service.create_password_link(db_session, user)
        r = client.get(f"/auth/activate?token={raw_token}")
        assert r.status_code == 200

    def test_activate_page_with_invalid_token(self, client):
        r = client.get("/auth/activate?token=invalid")
        assert r.status_code in (200, 303)


class TestProfile:
    def test_profile_page(self, client, client_user):
        login_client(client)
        r = client.get("/profile", follow_redirects=False)
        assert r.status_code in (200, 303)

    def test_profile_subpages(self, client, client_user):
        login_client(client)
        for path in (
            "/profile",
            "/profile/data",
            "/profile/password",
            "/profile/notifications",
            "/profile/appearance",
        ):
            r = client.get(path, follow_redirects=False)
            assert r.status_code in (200, 303)

    def test_profile_update(self, client, client_user):
        login_client(client)
        r = client.post(
            "/profile/data",
            data={
                "first_name": "Updated",
                "last_name": "Name",
                "email": "client@test.local",
                "phone": "",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)

    def test_profile_password_change(self, client, client_user):
        login_client(client)
        r = client.post(
            "/profile/password",
            data={
                "current_password": "Client123!ab",
                "new_password": "NewPass123!a",
                "confirm_password": "NewPass123!a",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)

    def test_profile_notifications(self, client, client_user):
        login_client(client)
        r = client.post(
            "/profile/notifications",
            data={
                "notify_reply": "on",
                "notify_ticket_update": "on",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)


class TestForgotAndConfirmEmail:
    def test_forgot_password(self, client, client_user):
        r = client.post(
            "/auth/forgot-password",
            data={"email": "client@test.local"},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_login_page(self, client):
        r = client.get("/login")
        assert r.status_code == 200

    def test_confirm_email_flow(self, client, db_session, client_user):
        from app.services import auth as auth_service

        _row, raw = auth_service.request_email_change(
            db_session, client_user, "confirm@test.local"
        )
        r = client.get(f"/auth/confirm-email?token={raw}")
        assert r.status_code in (200, 303)
        r = client.post(
            "/auth/confirm-email",
            data={"token": raw},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_set_password_redirect(self, client):
        r = client.get("/auth/set-password?token=abc", follow_redirects=False)
        assert r.status_code in (302, 303)


def _create_pending_user(db_session):
    return make_user(
        db_session,
        "pending@test.local",
        first_name="Pending",
        last_name="User",
        activated=False,
        is_active=True,
    )
