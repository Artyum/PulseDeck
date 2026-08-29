"""Add project.slug and ticket.number for human URLs.

Revision ID: 0002_slugs_numbers
Revises: 0001_initial
Create Date: 2026-07-28
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence
from typing import cast

import sqlalchemy as sa

from alembic import op

revision = "0002_slugs_numbers"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_CHAR_REPLACEMENTS = {
    "ą": "a",
    "ć": "c",
    "ę": "e",
    "ł": "l",
    "ń": "n",
    "ó": "o",
    "ś": "s",
    "ź": "z",
    "ż": "z",
}


def _slugify(text: str) -> str:
    s = (text or "").strip().lower()
    out: list[str] = []
    for ch in s:
        out.append(_CHAR_REPLACEMENTS.get(ch, ch))
    s = "".join(out)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return slug[:80].strip("-") or "projekt"


def upgrade() -> None:
    op.add_column("projects", sa.Column("slug", sa.String(length=100), nullable=True))
    op.add_column("tickets", sa.Column("number", sa.Integer(), nullable=True))

    bind = op.get_bind()
    projects = cast(
        Sequence[tuple[object, object]],
        bind.execute(sa.text("SELECT id, name FROM projects")).all(),
    )
    used: set[str] = set()
    for project_id_raw, name_raw in projects:
        project_id = uuid.UUID(str(project_id_raw))
        base = _slugify(str(name_raw))
        slug = base
        n = 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        _ = bind.execute(
            sa.text("UPDATE projects SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": project_id},
        )

    tickets = cast(
        Sequence[tuple[object, object]],
        bind.execute(
            sa.text(
                "SELECT id, project_id FROM tickets ORDER BY project_id, created_at, id"
            )
        ).all(),
    )
    counters: dict[uuid.UUID, int] = {}
    for ticket_id_raw, project_id_raw in tickets:
        ticket_id = uuid.UUID(str(ticket_id_raw))
        project_id = uuid.UUID(str(project_id_raw))
        counters[project_id] = counters.get(project_id, 0) + 1
        _ = bind.execute(
            sa.text("UPDATE tickets SET number = :num WHERE id = :id"),
            {"num": counters[project_id], "id": ticket_id},
        )

    op.alter_column(
        "projects", "slug", existing_type=sa.String(length=100), nullable=False
    )
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)

    op.alter_column("tickets", "number", existing_type=sa.Integer(), nullable=False)
    op.create_unique_constraint(
        "uq_ticket_project_number", "tickets", ["project_id", "number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_ticket_project_number", "tickets", type_="unique")
    op.drop_column("tickets", "number")
    op.drop_index("ix_projects_slug", table_name="projects")
    op.drop_column("projects", "slug")
