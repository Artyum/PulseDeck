from __future__ import annotations

from datetime import datetime, timezone

from app.models.enums import TicketPriority, TicketStatus, TicketType, UserRole
from app.models.user import User
from app.services import projects as project_service
from app.services import tickets as ticket_service
from app.services.auth import set_password

_DEFAULT_PASSWORDS = {
    UserRole.ADMIN: "Admin123!abcd",
    UserRole.STAFF: "Staff123!abcd",
    UserRole.USER: "Client123!ab",
}


def login(
    client,
    email: str,
    password: str,
    *,
    next_path: str | None = None,
    assert_ok: bool = True,
):
    data = {"email": email, "password": password}
    if next_path is not None:
        data["next"] = next_path
    response = client.post("/auth/login", data=data, follow_redirects=False)
    if assert_ok:
        assert response.status_code in (303, 200)
    return response


def login_admin(client):
    return login(client, "admin@test.local", "Admin123!abcd")


def login_client(client):
    return login(client, "client@test.local", "Client123!ab")


def login_staff(client):
    return login(client, "staff@test.local", "Staff123!abcd")


def make_user(
    db,
    email: str,
    *,
    first_name: str = "Test",
    last_name: str = "User",
    role: UserRole = UserRole.USER,
    password: str | None = None,
    project=None,
    activated: bool = True,
    **attrs,
) -> User:
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=role,
        activated_at=datetime.now(timezone.utc) if activated else None,
        **attrs,
    )
    if password is None and activated:
        password = _DEFAULT_PASSWORDS.get(role, "Test1234!abcd")
    if password is not None:
        set_password(user, password)
    db.add(user)
    db.commit()
    db.refresh(user)
    if project is not None:
        project_service.add_project_member(db, project.id, user.id)
    return user


def make_ticket(
    db,
    project,
    author,
    *,
    title: str = "Ticket",
    description: str = "Desc",
    ticket_type: TicketType = TicketType.BUG,
    priority: TicketPriority = TicketPriority.NORMAL,
    status: TicketStatus | None = None,
):
    ticket = ticket_service.create_ticket(
        db,
        project_id=project.id,
        author=author,
        title=title,
        description=description,
        ticket_type=ticket_type,
        priority=priority,
    )
    if status is not None and status != TicketStatus.NEW:
        ticket.status = status
        if status == TicketStatus.DONE:
            ticket.closed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(ticket)
    return ticket


def peer_participant_ticket(db, project, author, *, notify_reply: bool = True):
    peer = make_user(
        db,
        f"peer-{author.id}@test.local",
        first_name="Peer",
        last_name="Client",
        password="Peer1234!abcd",
        project=project,
    )
    ticket = make_ticket(db, project, author, title="Peer ticket")
    ticket_service.add_participant(db, ticket, author, peer.id)
    ticket = ticket_service.get_ticket(db, ticket.id)
    assert ticket is not None
    if notify_reply:
        peer.notify_reply = True
        db.commit()
    return ticket, peer
