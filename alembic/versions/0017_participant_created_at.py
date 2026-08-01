"""ticket_participants.created_at for watch order.

Revision ID: 0017_participant_created_at
Revises: 0016_reply_token_used_at
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0017_participant_created_at"
down_revision = "0016_reply_token_used_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("ticket_participants")}
    if "created_at" in cols:
        return
    op.add_column(
        "ticket_participants",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("ticket_participants", "created_at")
