"""User profile fields, is_active, magic token purpose.

Revision ID: 0006_user_profile_fields
Revises: 0005_uuid_pk_to_bigint
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_user_profile_fields"
down_revision = "0005_uuid_pk_to_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column(
        "users", sa.Column("pending_email", sa.String(length=320), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_epoch",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index("ix_users_pending_email", "users", ["pending_email"])
    op.add_column(
        "magic_tokens",
        sa.Column(
            "purpose",
            sa.String(length=32),
            nullable=False,
            server_default="login",
        ),
    )


def downgrade() -> None:
    op.drop_column("magic_tokens", "purpose")
    op.drop_index("ix_users_pending_email", table_name="users")
    op.drop_column("users", "auth_epoch")
    op.drop_column("users", "is_active")
    op.drop_column("users", "pending_email")
    op.drop_column("users", "phone")
