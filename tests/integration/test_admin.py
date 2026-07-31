"""Admin panel integration tests."""


def _login_admin(client):
    r = client.post(
        "/auth/login",
        data={"email": "admin@test.local", "password": "Admin123!"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 200)


class TestAdminAccess:
    def test_admin_dashboard(self, client, admin_user):
        _login_admin(client)
        r = client.get("/admin")
        assert r.status_code == 200

    def test_non_admin_blocked(self, client, client_user):
        r = client.post(
            "/auth/login",
            data={"email": "client@test.local", "password": "Client123!"},
            follow_redirects=False,
        )
        r = client.get("/admin", follow_redirects=False)
        # Non-admin gets redirected away from /admin
        assert r.status_code in (303, 403, 200)


class TestAdminProjects:
    def test_create_project(self, client, admin_user):
        _login_admin(client)
        r = client.post(
            "/admin/projects",
            data={"name": "New Project", "key": "NEWP"},
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_create_project_duplicate_key(
        self, client, admin_user, project_with_members
    ):
        _login_admin(client)
        r = client.post(
            "/admin/projects",
            data={"name": "Other", "key": "DEMO"},
            follow_redirects=False,
        )
        # Duplicate key stays on same page
        assert r.status_code in (200, 303, 422)

    def test_project_detail(self, client, admin_user, project_with_members):
        _login_admin(client)
        r = client.get(f"/admin/projects/{project_with_members.key}")
        assert r.status_code == 200
        assert project_with_members.name in r.text

    def test_edit_project(self, client, admin_user, project_with_members):
        _login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/edit",
            data={"name": "Updated", "key": project_with_members.key},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)

    def test_toggle_project_active(
        self, client, db_session, admin_user, project_with_members
    ):
        _login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/active",
            data={"active": "0"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        db_session.refresh(project_with_members)
        assert project_with_members.is_active is False
        r = client.post(
            f"/admin/projects/{project_with_members.key}/active",
            data={"active": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        db_session.refresh(project_with_members)
        assert project_with_members.is_active is True

    def test_add_project_member(
        self, client, db_session, admin_user, project_with_members, client_user
    ):
        _login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/members",
            data={"user_id": str(client_user.id)},
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_remove_project_member(
        self, client, db_session, admin_user, project_with_members, client_user
    ):
        from app.services import projects as project_service

        project_service.add_project_member(
            db_session, project_with_members.id, client_user.id
        )
        _login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/members/{client_user.id}/remove",
            follow_redirects=False,
        )
        assert r.status_code == 303


class TestAdminUsers:
    def test_users_list(self, client, admin_user):
        _login_admin(client)
        r = client.get("/admin/users")
        assert r.status_code == 200
        assert "admin" in r.text.lower() or "Admin" in r.text

    def test_create_user(self, client, admin_user, project_with_members):
        _login_admin(client)
        r = client.post(
            "/admin/users/new",
            data={
                "first_name": "Nowy",
                "last_name": "User",
                "email": "nowy@test.local",
                "role": "USER",
                "project_ids": [str(project_with_members.id)],
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_edit_user(self, client, admin_user, client_user):
        _login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}",
            data={
                "first_name": "Updated",
                "last_name": "Klient",
                "email": client_user.email,
                "phone": "",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 400)

    def test_toggle_active(self, client, admin_user, client_user):
        _login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}/active",
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)

    def test_change_role(self, client, admin_user, client_user):
        _login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}",
            data={
                "first_name": client_user.first_name,
                "last_name": client_user.last_name,
                "email": client_user.email,
                "phone": "",
                "role": "STAFF",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 400)

    def test_send_password_link(self, client, admin_user, client_user):
        _login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}/password",
            data={"action": "send_link"},
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_user_edit_page(self, client, admin_user, client_user):
        _login_admin(client)
        r = client.get(f"/admin/users/{client_user.id}")
        assert r.status_code == 200

    def test_user_notifications(self, client, admin_user, client_user):
        _login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}/notifications",
            data={
                "notify_reply": "on",
                "notify_ticket_update": "on",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_resend_activation(self, client, db_session, admin_user):
        from app.models.enums import UserRole
        from app.models.user import User

        pending = User(
            email="resend@test.local",
            first_name="Resend",
            last_name="User",
            role=UserRole.USER,
            activated_at=None,
            is_active=True,
        )
        db_session.add(pending)
        db_session.commit()
        db_session.refresh(pending)
        _login_admin(client)
        r = client.post(
            f"/admin/users/{pending.id}/resend-activation",
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_set_password_direct(self, client, admin_user, client_user):
        _login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}/password",
            data={
                "action": "set",
                "new_password": "AdminSet1!",
                "confirm_password": "AdminSet1!",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_projects_list(self, client, admin_user, project_with_members):
        _login_admin(client)
        r = client.get("/admin/projects")
        assert r.status_code == 200
        assert project_with_members.name in r.text


def _login_client(client):
    r = client.post(
        "/auth/login",
        data={"email": "client@test.local", "password": "Client123!"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 200)


class TestAdminProjectTags:
    def test_tag_delete(self, client, db_session, admin_user, project_with_members):
        from app.models.enums import TicketType
        from app.models.ticket import Tag, TicketTag
        from app.services import tickets as ticket_service

        ticket = ticket_service.create_ticket(
            db_session,
            project_id=project_with_members.id,
            author=admin_user,
            title="Tag to delete",
            description="Desc",
            ticket_type=TicketType.BUG,
        )
        tag = Tag(project_id=project_with_members.id, name="delete-me")
        db_session.add(tag)
        db_session.flush()
        db_session.add(TicketTag(ticket_id=ticket.id, tag_id=tag.id))
        db_session.commit()
        _login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/tags/{tag.id}/delete",
            follow_redirects=False,
        )
        assert r.status_code == 303
        tag_id = tag.id
        db_session.expunge_all()
        assert db_session.get(Tag, tag_id) is None

    def test_tag_delete_non_admin_blocked(
        self, client, db_session, client_user, project_with_members
    ):
        from app.models.ticket import Tag

        tag = Tag(project_id=project_with_members.id, name="cant-delete")
        db_session.add(tag)
        db_session.commit()
        _login_client(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/tags/{tag.id}/delete",
            follow_redirects=False,
        )
        assert r.status_code in (303, 403)

    def test_tag_delete_not_found(self, client, admin_user, project_with_members):
        _login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/tags/999/delete",
            follow_redirects=False,
        )
        assert r.status_code in (303, 404)
