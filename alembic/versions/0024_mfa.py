"""mfa challenges and trusted devices

Revision ID: 0024_mfa
Revises: 0023_notify_clients_staff
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0024_mfa"
down_revision = "0023_notify_clients_staff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mfa_challenges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mfa_challenges_user_id", "mfa_challenges", ["user_id"])
    op.create_index("ix_mfa_challenges_expires_at", "mfa_challenges", ["expires_at"])
    op.create_table(
        "mfa_trusted_devices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_mfa_trusted_devices_user_id", "mfa_trusted_devices", ["user_id"]
    )
    op.create_index(
        "ix_mfa_trusted_devices_expires_at", "mfa_trusted_devices", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_mfa_trusted_devices_expires_at", table_name="mfa_trusted_devices")
    op.drop_index("ix_mfa_trusted_devices_user_id", table_name="mfa_trusted_devices")
    op.drop_table("mfa_trusted_devices")
    op.drop_index("ix_mfa_challenges_expires_at", table_name="mfa_challenges")
    op.drop_index("ix_mfa_challenges_user_id", table_name="mfa_challenges")
    op.drop_table("mfa_challenges")
