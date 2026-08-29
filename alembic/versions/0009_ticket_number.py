"""Add tickets.number per project.

Revision ID: 0009_ticket_number
Revises: 0008_hash_magic_tokens
Create Date: 2026-07-30
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import sqlalchemy as sa

from alembic import op

revision = "0009_ticket_number"
down_revision = "0008_hash_magic_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("number", sa.Integer(), nullable=True))

    bind = op.get_bind()
    tickets = cast(
        Sequence[tuple[object, object]],
        bind.execute(
            sa.text(
                "SELECT id, project_id FROM tickets ORDER BY project_id, created_at, id"
            )
        ).all(),
    )
    counters: dict[object, int] = {}
    for ticket_id, project_id in tickets:
        counters[project_id] = counters.get(project_id, 0) + 1
        bind.execute(
            sa.text("UPDATE tickets SET number = :num WHERE id = :id"),
            {"num": counters[project_id], "id": ticket_id},
        )

    op.alter_column("tickets", "number", existing_type=sa.Integer(), nullable=False)
    op.create_unique_constraint(
        "uq_ticket_project_number", "tickets", ["project_id", "number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_ticket_project_number", "tickets", type_="unique")
    op.drop_column("tickets", "number")
