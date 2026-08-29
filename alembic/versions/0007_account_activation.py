"""Account activation: activated_at, drop invites, token defaults.

Revision ID: 0007_account_activation
Revises: 0006_user_profile_fields
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_account_activation"
down_revision = "0006_user_profile_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE users
        SET activated_at = created_at
        WHERE password_hash IS NOT NULL
        """
    )
    op.drop_table("invite_link_projects")
    op.drop_table("invite_links")
    op.alter_column(
        "magic_tokens",
        "purpose",
        existing_type=sa.String(length=32),
        server_default="password_set",
        existing_nullable=False,
    )
    op.execute(
        """
        UPDATE magic_tokens
        SET purpose = 'password_set'
        WHERE purpose = 'login'
        """
    )


def downgrade() -> None:
    op.alter_column(
        "magic_tokens",
        "purpose",
        existing_type=sa.String(length=32),
        server_default="login",
        existing_nullable=False,
    )
    op.create_table(
        "invite_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invite_links_token", "invite_links", ["token"], unique=True)
    op.create_table(
        "invite_link_projects",
        sa.Column("invite_id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["invite_id"], ["invite_links.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("invite_id", "project_id"),
    )
    op.drop_column("users", "activated_at")
