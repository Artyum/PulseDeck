"""Drop ticket reply tokens and magic_tokens.ticket_id.

Revision ID: 0026_drop_reply_tokens
Revises: 0025_project_member_role
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0026_drop_reply_tokens"
down_revision = "0025_project_member_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM magic_tokens WHERE purpose = 'ticket_reply'")
    op.drop_constraint(
        "fk_magic_tokens_ticket_id_tickets", "magic_tokens", type_="foreignkey"
    )
    op.drop_index("ix_magic_tokens_ticket_id", table_name="magic_tokens")
    op.drop_column("magic_tokens", "ticket_id")


def downgrade() -> None:
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
