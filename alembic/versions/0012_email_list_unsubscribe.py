"""Add email_outbox.list_unsubscribe_url for List-Unsubscribe headers.

Revision ID: 0012_email_list_unsubscribe
Revises: 0011_project_is_active
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_email_list_unsubscribe"
down_revision = "0011_project_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_outbox",
        sa.Column("list_unsubscribe_url", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_outbox", "list_unsubscribe_url")
