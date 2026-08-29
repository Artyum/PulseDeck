"""Support desk: priority, closed_at, internal notes, tags.

Revision ID: 0003_support_desk
Revises: 0002_slugs_numbers
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_support_desk"
down_revision = "0002_slugs_numbers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "priority", sa.String(length=20), nullable=False, server_default="NORMAL"
        ),
    )
    op.add_column(
        "tickets", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "comments",
        sa.Column(
            "is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_tag_project_name"),
    )
    op.create_index("ix_tags_project_id", "tags", ["project_id"])
    op.create_table(
        "ticket_tags",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticket_id", "tag_id"),
        sa.UniqueConstraint("ticket_id", "tag_id", name="uq_ticket_tag"),
    )
    op.alter_column("tickets", "priority", server_default=None)
    op.alter_column("comments", "is_internal", server_default=None)


def downgrade() -> None:
    op.drop_table("ticket_tags")
    op.drop_index("ix_tags_project_id", table_name="tags")
    op.drop_table("tags")
    op.drop_column("comments", "is_internal")
    op.drop_column("tickets", "closed_at")
    op.drop_column("tickets", "priority")
