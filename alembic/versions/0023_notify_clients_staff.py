"""Add projects.notify_clients_on_staff_ticket.

Revision ID: 0023_notify_clients_staff
Revises: 0022_ticket_events
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0023_notify_clients_staff"
down_revision = "0022_ticket_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {col["name"] for col in inspect(bind).get_columns("projects")}
    if "notify_clients_on_staff_ticket" in columns:
        return
    op.add_column(
        "projects",
        sa.Column(
            "notify_clients_on_staff_ticket",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "notify_clients_on_staff_ticket")
