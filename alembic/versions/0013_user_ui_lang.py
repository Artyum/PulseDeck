"""Add users.ui_lang for email localization.

Revision ID: 0013_user_ui_lang
Revises: 0012_email_list_unsubscribe
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013_user_ui_lang"
down_revision = "0012_email_list_unsubscribe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "ui_lang",
            sa.String(length=8),
            nullable=False,
            server_default="en",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "ui_lang")
