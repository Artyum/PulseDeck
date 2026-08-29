"""Add projects.is_active for soft disable.

Revision ID: 0011_project_is_active
Revises: 0010_email_outbox_notify_prefs
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_project_is_active"
down_revision = "0010_email_outbox_notify_prefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "is_active")
