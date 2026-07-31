"""Add comments.edited_at and comments.edited_by_id.

Revision ID: 0014_comment_edited
Revises: 0013_user_ui_lang
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_comment_edited"
down_revision = "0013_user_ui_lang"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "comments",
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "comments",
        sa.Column("edited_by_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "comments_edited_by_id_fkey",
        "comments",
        "users",
        ["edited_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("comments_edited_by_id_fkey", "comments", type_="foreignkey")
    op.drop_column("comments", "edited_by_id")
    op.drop_column("comments", "edited_at")
