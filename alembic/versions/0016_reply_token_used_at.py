"""magic_tokens used_at + ticket_id for ticket_reply tokens.

Revision ID: 0016_reply_token_used_at
Revises: 0015_user_datetime_prefs
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016_reply_token_used_at"
down_revision = "0015_user_datetime_prefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "magic_tokens",
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE magic_tokens
            SET used_at = COALESCE(created_at, NOW())
            WHERE used IS TRUE
            """
        )
    )
    op.drop_column("magic_tokens", "used")
    op.add_column(
        "magic_tokens",
        sa.Column("ticket_id", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_magic_tokens_ticket_id", "magic_tokens", ["ticket_id"])
    op.create_foreign_key(
        "fk_magic_tokens_ticket_id_tickets",
        "magic_tokens",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_magic_tokens_ticket_id_tickets", "magic_tokens", type_="foreignkey"
    )
    op.drop_index("ix_magic_tokens_ticket_id", table_name="magic_tokens")
    op.drop_column("magic_tokens", "ticket_id")
    op.add_column(
        "magic_tokens",
        sa.Column(
            "used", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE magic_tokens
            SET used = TRUE
            WHERE used_at IS NOT NULL
            """
        )
    )
    op.alter_column("magic_tokens", "used", server_default=None)
    op.drop_column("magic_tokens", "used_at")
