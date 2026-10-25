"""Project membership role; account role is admin or user.

Revision ID: 0025_project_member_role
Revises: 0024_mfa
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0025_project_member_role"
down_revision = "0024_mfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_members",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="CLIENT",
        ),
    )
    op.execute(
        """
        UPDATE project_members
        SET role = 'STAFF'
        WHERE user_id IN (
            SELECT id FROM users WHERE role IN ('STAFF', 'ADMIN')
        )
        """
    )
    op.execute("UPDATE users SET role = 'USER' WHERE role = 'STAFF'")


def downgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET role = 'STAFF'
        WHERE role = 'USER'
          AND id IN (
              SELECT user_id FROM project_members WHERE role = 'STAFF'
          )
        """
    )
    op.drop_column("project_members", "role")
