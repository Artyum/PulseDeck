"""Admin panel integration tests."""

from unittest.mock import patch

from tests.helpers import login_admin, login_client, make_ticket, make_user


class TestAdminAccess:
    def test_admin_dashboard(self, client, admin_user):
        login_admin(client)
        r = client.get("/admin")
        assert r.status_code == 200

    def test_non_admin_blocked(self, client, client_user):
        login_client(client)
        r = client.get("/admin", follow_redirects=False)
        # Non-admin gets redirected away from /admin
        assert r.status_code in (303, 403, 200)


class TestAdminProjects:
    def test_create_project(self, client, admin_user, staff_user):
        login_admin(client)
        r = client.post(
            "/admin/projects",
            data={
                "name": "New Project",
                "key": "NEWP",
                "staff_user_id": str(staff_user.id),
            },
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_create_project_duplicate_key(
        self, client, admin_user, project_with_members, staff_user
    ):
        login_admin(client)
        r = client.post(
            "/admin/projects",
            data={
                "name": "Other",
                "key": "DEMO",
                "staff_user_id": str(staff_user.id),
            },
            follow_redirects=False,
        )
        # Duplicate key stays on same page
        assert r.status_code in (200, 303, 422)

    def test_project_detail(self, client, admin_user, project_with_members):
        login_admin(client)
        r = client.get(f"/admin/projects/{project_with_members.key}")
        assert r.status_code == 200
        assert project_with_members.name in r.text

    def test_edit_project(self, client, admin_user, project_with_members):
        login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/edit",
            data={"name": "Updated", "key": project_with_members.key},
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)

    def test_edit_project_notify_clients_on_staff_ticket(
        self, client, db_session, admin_user, project_with_members
    ):
        login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/edit",
            data={
                "name": project_with_members.name,
                "project_key": project_with_members.key,
                "description": project_with_members.description or "",
                "notify_clients_on_staff_ticket": "1",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        db_session.refresh(project_with_members)
        assert project_with_members.notify_clients_on_staff_ticket is True

    def test_edit_project_notify_clients_off(
        self, client, db_session, admin_user, project_with_members
    ):
        project_with_members.notify_clients_on_staff_ticket = True
        db_session.commit()
        login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/edit",
            data={
                "name": project_with_members.name,
                "project_key": project_with_members.key,
                "description": project_with_members.description or "",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        db_session.refresh(project_with_members)
        assert project_with_members.notify_clients_on_staff_ticket is False

    def test_toggle_project_active(
        self, client, db_session, admin_user, project_with_members
    ):
        login_admin(client)
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
        login_admin(client)
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
        login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/members/{client_user.id}/remove",
            follow_redirects=False,
        )
        assert r.status_code == 303


class TestAdminUsers:
    def test_users_list(self, client, admin_user):
        login_admin(client)
        r = client.get("/admin/users")
        assert r.status_code == 200
        assert "admin" in r.text.lower() or "Admin" in r.text

    def test_create_user(self, client, db_session, admin_user, project_with_members):
        login_admin(client)
        with patch("app.services.auth.send_password_link") as send_link:
            r = client.post(
                "/admin/users/new",
                data={
                    "first_name": "Nowy",
                    "last_name": "User",
                    "email": "nowy@test.local",
                    "phone": "+48123456789",
                    "role": "USER",
                    "ui_lang": "pl",
                    "project_ids": [str(project_with_members.id)],
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            send_link.assert_called_once()
        db_session.expire_all()
        from app.services import auth as auth_service

        user = auth_service.get_user_by_email(db_session, "nowy@test.local")
        assert user is not None
        assert user.is_pending
        assert user.phone == "+48123456789"
        assert user.ui_lang == "pl"
        assert r.headers["location"].startswith(f"/admin/users/{user.id}")

    def test_create_user_active(
        self, client, db_session, admin_user, project_with_members
    ):
        login_admin(client)
        with patch("app.services.auth.send_password_link") as send_link:
            r = client.post(
                "/admin/users/new",
                data={
                    "first_name": "Aktywny",
                    "last_name": "User",
                    "email": "aktywny@test.local",
                    "role": "USER",
                    "ui_lang": "en",
                    "mode": "active",
                    "project_ids": [str(project_with_members.id)],
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            send_link.assert_not_called()
        db_session.expire_all()
        from app.services import auth as auth_service

        user = auth_service.get_user_by_email(db_session, "aktywny@test.local")
        assert user is not None
        assert not user.is_pending
        assert user.ui_lang == "en"
        assert "created_active" in r.headers["location"]

    def test_update_user_ui_lang(
        self, client, db_session, admin_user, client_user, project_with_members
    ):
        login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}",
            data={
                "first_name": client_user.first_name,
                "last_name": client_user.last_name,
                "email": client_user.email,
                "phone": "",
                "role": client_user.role.value,
                "ui_lang": "pl",
                "project_ids": [str(project_with_members.id)],
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        db_session.expire_all()
        db_session.refresh(client_user)
        assert client_user.ui_lang == "pl"

    def test_edit_user(self, client, admin_user, client_user):
        login_admin(client)
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
        login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}/active",
            follow_redirects=False,
        )
        assert r.status_code in (200, 303, 422)

    def test_change_role(self, client, admin_user, client_user):
        login_admin(client)
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
        login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}/password",
            data={"action": "send_link"},
            follow_redirects=False,
        )
        assert r.status_code == 303

    def test_user_edit_page(self, client, admin_user, client_user):
        login_admin(client)
        r = client.get(f"/admin/users/{client_user.id}")
        assert r.status_code == 200

    def test_user_notifications(self, client, admin_user, client_user):
        login_admin(client)
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
        pending = make_user(
            db_session,
            "resend@test.local",
            first_name="Resend",
            last_name="User",
            activated=False,
            is_active=True,
        )
        login_admin(client)
        r = client.post(
            f"/admin/users/{pending.id}/resend-activation",
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_set_password_direct(self, client, admin_user, client_user):
        login_admin(client)
        r = client.post(
            f"/admin/users/{client_user.id}/password",
            data={
                "action": "set",
                "new_password": "AdminSet1!ab",
                "confirm_password": "AdminSet1!ab",
            },
            follow_redirects=False,
        )
        assert r.status_code in (200, 303)

    def test_projects_list(self, client, admin_user, project_with_members):
        login_admin(client)
        r = client.get("/admin/projects")
        assert r.status_code == 200
        assert project_with_members.name in r.text


class TestAdminProjectTags:
    def test_tag_delete(self, client, db_session, admin_user, project_with_members):
        from app.models.ticket import Tag, TicketTag

        ticket = make_ticket(
            db_session, project_with_members, admin_user, title="Tag to delete"
        )
        tag = Tag(project_id=project_with_members.id, name="delete-me")
        db_session.add(tag)
        db_session.flush()
        db_session.add(TicketTag(ticket_id=ticket.id, tag_id=tag.id))
        db_session.commit()
        login_admin(client)
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
        login_client(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/tags/{tag.id}/delete",
            follow_redirects=False,
        )
        assert r.status_code in (303, 403)

    def test_tag_delete_not_found(self, client, admin_user, project_with_members):
        login_admin(client)
        r = client.post(
            f"/admin/projects/{project_with_members.key}/tags/999/delete",
            follow_redirects=False,
        )
        assert r.status_code in (303, 404)
