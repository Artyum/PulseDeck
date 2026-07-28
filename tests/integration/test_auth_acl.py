from app.models.enums import TicketStatus, TicketType
from app.services import tickets as ticket_service


def _login(client, email: str, password: str):
    r = client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert r.status_code in (303, 200)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_and_feed(client, admin_user, client_user, project_with_members):
    _login(client, "client@test.local", "Client123!")
    r = client.get(f"/p/{project_with_members.key}")
    assert r.status_code == 200
    assert "Demo" in r.text


def test_admin_requires_admin(client, client_user, project_with_members):
    _login(client, "client@test.local", "Client123!")
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code in (303, 403, 401)


def test_comment_acl(
    client, db_session, admin_user, client_user, staff_user, project_with_members
):
    from app.models.enums import UserRole
    from app.models.user import User
    from app.services import projects as project_service
    from app.services.auth import set_password

    other2 = User(
        email="other@test.local",
        first_name="Inny",
        last_name="Klient",
        role=UserRole.USER,
    )
    set_password(other2, "Client123!")
    db_session.add(other2)
    db_session.commit()
    db_session.refresh(other2)
    project_service.add_project_member(db_session, project_with_members.id, other2.id)

    ticket = ticket_service.create_ticket(
        db_session,
        project_id=project_with_members.id,
        author=client_user,
        title="Bug",
        description="Opis",
        ticket_type=TicketType.BUG,
    )
    assert ticket_service.can_comment(db_session, client_user, ticket) is True
    assert ticket_service.can_comment(db_session, other2, ticket) is True
    assert ticket_service.can_comment(db_session, staff_user, ticket) is True

    ticket_service.set_status(db_session, ticket, staff_user, TicketStatus.DONE)
    ticket = ticket_service.get_ticket(db_session, ticket.id)
    assert ticket is not None
    assert ticket_service.can_comment(db_session, other2, ticket) is False


def test_staff_reply_sets_waiting_on_client(
    client, db_session, client_user, staff_user, project_with_members
):
    ticket = ticket_service.create_ticket(
        db_session,
        project_id=project_with_members.id,
        author=client_user,
        title="Pytanie",
        description="Jak?",
        ticket_type=TicketType.QUESTION,
    )
    assert ticket.status == TicketStatus.NEW
    ticket_service.add_comment(db_session, ticket, staff_user, "Pracujemy nad tym")
    ticket = ticket_service.get_ticket(db_session, ticket.id)
    assert ticket is not None
    assert ticket.status == TicketStatus.WAITING_ON_CLIENT
    assert ticket.assignee_id == staff_user.id

    ticket_service.add_comment(db_session, ticket, client_user, "Dzięki")
    ticket = ticket_service.get_ticket(db_session, ticket.id)
    assert ticket is not None
    assert ticket.status == TicketStatus.IN_PROGRESS

    prev = ticket.status
    ticket_service.add_comment(
        db_session, ticket, staff_user, "Notatka", is_internal=True
    )
    ticket = ticket_service.get_ticket(db_session, ticket.id)
    assert ticket is not None
    assert ticket.status == prev


def test_invite_register(client, db_session, admin_user, project_with_members):
    from app.services import projects as project_service

    invite = project_service.create_invite(
        db_session,
        created_by=admin_user,
        project_ids=[project_with_members.id],
        expires_days=7,
        max_uses=5,
    )
    r = client.post(
        f"/invite/{invite.token}",
        data={
            "first_name": "Nowy",
            "last_name": "User",
            "email": "nowy@test.local",
            "password": "NowyUser1!",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"
