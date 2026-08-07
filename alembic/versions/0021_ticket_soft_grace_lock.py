"""Ticket soft-delete and author grace-edit lock.

Revision ID: 0021_ticket_soft_grace_lock
Revises: 0020_user_last_login_at
Create Date: 2026-08-06
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0021_ticket_soft_grace_lock"
down_revision = "0020_user_last_login_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("author_edits_locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("deleted_by_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "tickets_deleted_by_id_fkey",
        "tickets",
        "users",
        ["deleted_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tickets_deleted_at", "tickets", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_tickets_deleted_at", table_name="tickets")
    op.drop_constraint("tickets_deleted_by_id_fkey", "tickets", type_="foreignkey")
    op.drop_column("tickets", "deleted_by_id")
    op.drop_column("tickets", "deleted_at")
    op.drop_column("tickets", "author_edits_locked_at")
