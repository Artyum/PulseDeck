"""Add users.last_login_at.

Revision ID: 0020_user_last_login_at
Revises: 0019_portal_settings
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0020_user_last_login_at"
down_revision = "0019_portal_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_login_at")
