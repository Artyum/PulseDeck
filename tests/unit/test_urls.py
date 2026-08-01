from typing import cast

import pytest

from app.models.ticket import Ticket
from app.models.user import Project
from app.utils.urls import (
    admin_project_path,
    attachment_path,
    project_path,
    safe_next_path,
    ticket_label,
    ticket_path,
)


class TestProjectPath:
    def test_returns_path_with_key(self):
        project = cast(Project, type("Project", (), {"key": "DEMO"})())
        assert project_path(project) == "/p/DEMO"


class TestTicketLabel:
    def test_with_project(self):
        project = cast(Project, type("Project", (), {"key": "DEMO"})())
        ticket = cast(Ticket, type("Ticket", (), {"number": 42, "project": project})())
        assert ticket_label(ticket) == "DEMO-42"

    def test_without_project_raises(self):
        ticket = cast(Ticket, type("Ticket", (), {"number": 42, "project": None})())
        with pytest.raises(ValueError, match="ticket.project.key is required"):
            ticket_label(ticket)


class TestTicketPath:
    def test_returns_path(self):
        project = cast(Project, type("Project", (), {"key": "DEMO"})())
        ticket = cast(Ticket, type("Ticket", (), {"number": 42, "project": project})())
        assert ticket_path(ticket) == "/t/DEMO-42"


class TestAdminProjectPath:
    def test_returns_path(self):
        project = cast(Project, type("Project", (), {"key": "DEMO"})())
        assert admin_project_path(project) == "/admin/projects/DEMO"


class TestAttachmentPath:
    def test_returns_path(self):
        from app.models.ticket import Attachment

        att = cast(Attachment, type("Attachment", (), {"id": 7})())
        assert attachment_path(att) == "/files/7"


class TestSafeNextPath:
    def test_valid_relative(self):
        assert safe_next_path("/t/DEMO-1") == "/t/DEMO-1"

    def test_empty_uses_default(self):
        assert safe_next_path("") == "/"
        assert safe_next_path(None) == "/"

    def test_rejects_open_redirect(self):
        assert safe_next_path("//evil.test") == "/"
        assert safe_next_path("https://evil.test") == "/"
        assert safe_next_path("/\\evil") == "/"
