"""Project key + ticket bigint PK; drop ticket.number.

Revision ID: 0004_project_key_ticket_bigint
Revises: 0003_support_desk
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import sqlalchemy as sa

from alembic import op

revision = "0004_project_key_ticket_bigint"
down_revision = "0003_support_desk"
branch_labels = None
depends_on = None


def _unique_key(base: str, used: set[str]) -> str:
    cleaned = "".join(ch for ch in (base or "").upper() if ch.isalnum())[:10]
    if len(cleaned) < 3:
        cleaned = (cleaned + "XXX")[:3]
    key = cleaned
    n = 2
    while key in used:
        suffix = str(n)
        key = (cleaned[: max(1, 10 - len(suffix))] + suffix)[:10]
        n += 1
    used.add(key)
    return key


def _drop_constraints(table: str, *, contypes: str) -> None:
    bind = op.get_bind()
    type_list = ", ".join(f"'{c}'" for c in contypes)
    rows = bind.execute(
        sa.text(
            f"""
            SELECT conname, contype
            FROM pg_constraint
            WHERE conrelid = '{table}'::regclass
              AND contype IN ({type_list})
            """
        )
    ).all()
    for conname, contype in rows:
        kind = {"p": "primary", "u": "unique", "f": "foreignkey"}[contype]
        op.drop_constraint(conname, table, type_=kind)


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("projects", sa.Column("key", sa.String(length=10), nullable=True))
    rows = cast(
        Sequence[tuple[object, object]],
        bind.execute(sa.text("SELECT id, slug FROM projects")).all(),
    )
    used: set[str] = set()
    for project_id, slug in rows:
        key = _unique_key(str(slug or ""), used)
        bind.execute(
            sa.text("UPDATE projects SET key = :key WHERE id = :id"),
            {"key": key, "id": project_id},
        )
    op.alter_column(
        "projects", "key", existing_type=sa.String(length=10), nullable=False
    )
    op.drop_index("ix_projects_slug", table_name="projects")
    op.drop_column("projects", "slug")
    op.create_index("ix_projects_key", "projects", ["key"], unique=True)
    op.execute(
        sa.text("CREATE UNIQUE INDEX uq_projects_name_lower ON projects (lower(name))")
    )

    op.execute(sa.text("CREATE SEQUENCE tickets_id_seq"))
    op.add_column("tickets", sa.Column("id_new", sa.BigInteger(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE tickets SET id_new = nextval('tickets_id_seq') WHERE id_new IS NULL"
        )
    )
    op.execute(
        sa.text(
            "SELECT setval('tickets_id_seq', COALESCE((SELECT MAX(id_new) FROM tickets), 1))"
        )
    )
    op.alter_column("tickets", "id_new", existing_type=sa.BigInteger(), nullable=False)

    for table in ("comments", "attachments", "ticket_participants", "ticket_tags"):
        op.add_column(table, sa.Column("ticket_id_new", sa.BigInteger(), nullable=True))
        op.execute(
            sa.text(
                f"UPDATE {table} AS c SET ticket_id_new = t.id_new "
                f"FROM tickets t WHERE c.ticket_id IS NOT NULL AND c.ticket_id = t.id"
            )
        )

    _drop_constraints("ticket_tags", contypes="f")
    _drop_constraints("ticket_participants", contypes="f")
    op.drop_constraint("comments_ticket_id_fkey", "comments", type_="foreignkey")
    op.drop_constraint("attachments_ticket_id_fkey", "attachments", type_="foreignkey")

    _drop_constraints("ticket_tags", contypes="pu")
    op.drop_column("ticket_tags", "ticket_id")
    op.alter_column(
        "ticket_tags",
        "ticket_id_new",
        new_column_name="ticket_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_primary_key("ticket_tags_pkey", "ticket_tags", ["ticket_id", "tag_id"])
    op.create_unique_constraint("uq_ticket_tag", "ticket_tags", ["ticket_id", "tag_id"])

    _drop_constraints("ticket_participants", contypes="pu")
    op.drop_column("ticket_participants", "ticket_id")
    op.alter_column(
        "ticket_participants",
        "ticket_id_new",
        new_column_name="ticket_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_primary_key(
        "ticket_participants_pkey", "ticket_participants", ["ticket_id", "user_id"]
    )
    op.create_unique_constraint(
        "uq_ticket_participant", "ticket_participants", ["ticket_id", "user_id"]
    )

    op.drop_index("ix_comments_ticket_id", table_name="comments")
    op.drop_column("comments", "ticket_id")
    op.alter_column(
        "comments",
        "ticket_id_new",
        new_column_name="ticket_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_index("ix_comments_ticket_id", "comments", ["ticket_id"])

    op.drop_index("ix_attachments_ticket_id", table_name="attachments")
    op.drop_column("attachments", "ticket_id")
    op.alter_column(
        "attachments",
        "ticket_id_new",
        new_column_name="ticket_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.create_index("ix_attachments_ticket_id", "attachments", ["ticket_id"])

    op.drop_constraint("uq_ticket_project_number", "tickets", type_="unique")
    op.drop_constraint("tickets_pkey", "tickets", type_="primary")
    op.drop_column("tickets", "id")
    op.drop_column("tickets", "number")
    op.alter_column(
        "tickets",
        "id_new",
        new_column_name="id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_primary_key("tickets_pkey", "tickets", ["id"])
    op.execute(sa.text("ALTER SEQUENCE tickets_id_seq OWNED BY tickets.id"))
    op.execute(
        sa.text(
            "ALTER TABLE tickets ALTER COLUMN id SET DEFAULT nextval('tickets_id_seq')"
        )
    )

    op.create_foreign_key(
        "ticket_tags_ticket_id_fkey",
        "ticket_tags",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "ticket_tags_tag_id_fkey",
        "ticket_tags",
        "tags",
        ["tag_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "ticket_participants_ticket_id_fkey",
        "ticket_participants",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "ticket_participants_user_id_fkey",
        "ticket_participants",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "comments_ticket_id_fkey",
        "comments",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "attachments_ticket_id_fkey",
        "attachments",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    raise NotImplementedError("Irreversible: UUID ticket PKs and project slugs removed")
