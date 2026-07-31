"""Add user datetime display preferences.

Revision ID: 0015_user_datetime_prefs
Revises: 0014_comment_edited
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_user_datetime_prefs"
down_revision = "0014_comment_edited"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "datetime_format",
            sa.String(length=16),
            nullable=False,
            server_default="ISO_8601",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="UTC",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "datetime_prefs_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE users SET timezone = 'Europe/Warsaw', "
            "datetime_format = 'ISO_8601', datetime_prefs_locked = true"
        )
    )


def downgrade() -> None:
    op.drop_column("users", "datetime_prefs_locked")
    op.drop_column("users", "timezone")
    op.drop_column("users", "datetime_format")
