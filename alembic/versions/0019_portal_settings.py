"""Portal settings key-value store.

Revision ID: 0019_portal_settings
Revises: 0018_rename_ticket_types
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0019_portal_settings"
down_revision = "0018_rename_ticket_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("portal_settings")
