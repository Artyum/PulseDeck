import pytest

from app.utils.urls import project_path, ticket_label, ticket_path, admin_project_path


class TestProjectPath:
    def test_returns_path_with_key(self):
        project = type("Project", (), {"key": "DEMO"})()
        assert project_path(project) == "/p/DEMO"


class TestTicketLabel:
    def test_with_project(self):
        project = type("Project", (), {"key": "DEMO"})()
        ticket = type("Ticket", (), {"id": 42, "project": project})()
        assert ticket_label(ticket) == "DEMO-42"

    def test_without_project_raises(self):
        ticket = type("Ticket", (), {"id": 42, "project": None})()
        with pytest.raises(ValueError, match="ticket.project.key is required"):
            ticket_label(ticket)


class TestTicketPath:
    def test_returns_path(self):
        project = type("Project", (), {"key": "DEMO"})()
        ticket = type("Ticket", (), {"id": 42, "project": project})()
        assert ticket_path(ticket) == "/t/DEMO-42"


class TestAdminProjectPath:
    def test_returns_path(self):
        project = type("Project", (), {"key": "DEMO"})()
        assert admin_project_path(project) == "/admin/projects/DEMO"
