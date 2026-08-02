"""Rename ticket types SUGGESTION→CHANGE, OTHER→TASK.

Revision ID: 0018_rename_ticket_types
Revises: 0017_participant_created_at
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op

revision = "0018_rename_ticket_types"
down_revision = "0017_participant_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE tickets SET type = 'CHANGE' WHERE type = 'SUGGESTION'")
    op.execute("UPDATE tickets SET type = 'TASK' WHERE type = 'OTHER'")


def downgrade() -> None:
    op.execute("UPDATE tickets SET type = 'SUGGESTION' WHERE type = 'CHANGE'")
    op.execute("UPDATE tickets SET type = 'OTHER' WHERE type = 'TASK'")
