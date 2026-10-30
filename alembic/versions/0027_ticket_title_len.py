"""Limit ticket title to 150 characters.

Revision ID: 0027_ticket_title_len
Revises: 0026_drop_reply_tokens
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027_ticket_title_len"
down_revision = "0026_drop_reply_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE tickets SET title = left(title, 150) WHERE char_length(title) > 150"
    )
    op.alter_column(
        "tickets",
        "title",
        existing_type=sa.String(length=300),
        type_=sa.String(length=150),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tickets",
        "title",
        existing_type=sa.String(length=150),
        type_=sa.String(length=300),
        existing_nullable=False,
    )
