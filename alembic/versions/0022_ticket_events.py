"""Ticket event history log.

Revision ID: 0022_ticket_events
Revises: 0021_ticket_soft_grace_lock
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022_ticket_events"
down_revision = "0021_ticket_soft_grace_lock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticket_events_ticket_id"), "ticket_events", ["ticket_id"], unique=False
    )
    op.create_index(
        op.f("ix_ticket_events_actor_id"), "ticket_events", ["actor_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_events_actor_id"), table_name="ticket_events")
    op.drop_index(op.f("ix_ticket_events_ticket_id"), table_name="ticket_events")
    op.drop_table("ticket_events")
