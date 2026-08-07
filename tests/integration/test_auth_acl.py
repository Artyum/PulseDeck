from app.models.enums import TicketStatus, TicketType
from app.services import tickets as ticket_service
from tests.helpers import login_client, make_ticket, make_user


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_and_feed(client, admin_user, client_user, project_with_members):
    login_client(client)
    r = client.get(f"/p/{project_with_members.key}")
    assert r.status_code == 200
    assert "Demo" in r.text


def test_admin_requires_admin(client, client_user, project_with_members):
    login_client(client)
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code in (303, 403, 401)


def test_comment_acl(
    client, db_session, admin_user, client_user, staff_user, project_with_members
):
    other2 = make_user(
        db_session,
        "other@test.local",
        first_name="Inny",
        last_name="Klient",
        project=project_with_members,
    )

    ticket = make_ticket(
        db_session, project_with_members, client_user, title="Bug", description="Opis"
    )
    assert ticket_service.can_comment(db_session, client_user, ticket) is True
    assert ticket_service.can_comment(db_session, other2, ticket) is False
    assert ticket_service.can_comment(db_session, staff_user, ticket) is True

    ticket_service.add_participant(db_session, ticket, client_user, other2.id)
    ticket = ticket_service.get_ticket(db_session, ticket.id)
    assert ticket is not None
    assert ticket_service.can_comment(db_session, other2, ticket) is True

    ticket_service.set_status(db_session, ticket, staff_user, TicketStatus.DONE)
    ticket = ticket_service.get_ticket(db_session, ticket.id)
    assert ticket is not None
    assert ticket_service.can_comment(db_session, other2, ticket) is False


def test_staff_reply_sets_waiting_on_client(
    client, db_session, client_user, staff_user, project_with_members
):
    ticket = make_ticket(
        db_session,
        project_with_members,
        client_user,
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


def test_user_activation(client, db_session, admin_user, project_with_members):
    from app.models.enums import MagicTokenPurpose, UserRole
    from app.services import auth as auth_service

    user = auth_service.create_user(
        db_session,
        first_name="Nowy",
        last_name="User",
        email="nowy@test.local",
        role=UserRole.USER,
        project_ids=[project_with_members.id],
    )
    token_row, raw_token = auth_service.create_password_link(db_session, user)
    assert token_row.purpose == MagicTokenPurpose.PASSWORD_SET.value
    r = client.post(
        "/auth/activate",
        data={
            "token": raw_token,
            "new_password": "NowyUser1!ab",
            "confirm_password": "NowyUser1!ab",
            "phone": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    db_session.refresh(user)
    assert user.activated_at is not None
    assert user.password_hash is not None
