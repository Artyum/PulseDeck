"""Convert remaining UUID PKs/FKs to bigint.

Revision ID: 0005_uuid_pk_to_bigint
Revises: 0004_project_key_ticket_bigint
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_uuid_pk_to_bigint"
down_revision = "0004_project_key_ticket_bigint"
branch_labels = None
depends_on = None

_PK_TABLES = (
    "users",
    "projects",
    "comments",
    "tags",
    "attachments",
    "magic_tokens",
    "invite_links",
)

# (child_table, old_fk_col, parent_table, nullable)
_FK_REMAPS = (
    ("project_members", "project_id", "projects", False),
    ("project_members", "user_id", "users", False),
    ("tickets", "project_id", "projects", False),
    ("tickets", "author_id", "users", False),
    ("tickets", "assignee_id", "users", True),
    ("ticket_participants", "user_id", "users", False),
    ("comments", "author_id", "users", False),
    ("tags", "project_id", "projects", False),
    ("ticket_tags", "tag_id", "tags", False),
    ("attachments", "comment_id", "comments", True),
    ("magic_tokens", "user_id", "users", False),
    ("invite_links", "created_by_id", "users", False),
    ("invite_link_projects", "invite_id", "invite_links", False),
    ("invite_link_projects", "project_id", "projects", False),
)

_COMPOSITE_PK_TABLES = (
    "project_members",
    "ticket_participants",
    "ticket_tags",
    "invite_link_projects",
)


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


def _drop_all_fks_involving(*tables: str) -> None:
    bind = op.get_bind()
    for table in tables:
        rows = bind.execute(
            sa.text(
                f"""
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = '{table}'::regclass
                  AND contype = 'f'
                """
            )
        ).all()
        for (conname,) in rows:
            op.drop_constraint(conname, table, type_="foreignkey")


def _swap_pk(table: str) -> None:
    seq = f"{table}_id_seq"
    op.execute(sa.text(f"CREATE SEQUENCE {seq}"))
    op.add_column(table, sa.Column("id_new", sa.BigInteger(), nullable=True))
    op.execute(
        sa.text(f"UPDATE {table} SET id_new = nextval('{seq}') WHERE id_new IS NULL")
    )
    op.execute(
        sa.text(
            f"SELECT setval('{seq}', COALESCE((SELECT MAX(id_new) FROM {table}), 1))"
        )
    )
    op.alter_column(table, "id_new", existing_type=sa.BigInteger(), nullable=False)


def _map_fk(child: str, col: str, parent: str) -> None:
    new_col = f"{col}_new"
    op.add_column(child, sa.Column(new_col, sa.BigInteger(), nullable=True))
    op.execute(
        sa.text(
            f"UPDATE {child} AS c SET {new_col} = p.id_new "
            f"FROM {parent} p WHERE c.{col} IS NOT NULL AND c.{col} = p.id"
        )
    )


def _finalize_pk(table: str) -> None:
    seq = f"{table}_id_seq"
    _drop_constraints(table, contypes="p")
    op.drop_column(table, "id")
    op.alter_column(
        table,
        "id_new",
        new_column_name="id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_primary_key(f"{table}_pkey", table, ["id"])
    op.execute(sa.text(f"ALTER SEQUENCE {seq} OWNED BY {table}.id"))
    op.execute(
        sa.text(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('{seq}')")
    )


def _finalize_fk(child: str, col: str, *, nullable: bool) -> None:
    new_col = f"{col}_new"
    index_name = f"ix_{child}_{col}"
    existing = (
        op.get_bind()
        .execute(
            sa.text(
                f"""
            SELECT 1 FROM pg_indexes
            WHERE tablename = '{child}' AND indexname = '{index_name}'
            """
            )
        )
        .first()
    )
    if existing:
        op.drop_index(index_name, table_name=child)

    op.drop_column(child, col)
    op.alter_column(
        child,
        new_col,
        new_column_name=col,
        existing_type=sa.BigInteger(),
        nullable=nullable,
    )


def upgrade() -> None:
    for table in _PK_TABLES:
        _swap_pk(table)

    for child, col, parent, _nullable in _FK_REMAPS:
        _map_fk(child, col, parent)

    affected = {
        "users",
        "projects",
        "comments",
        "tags",
        "attachments",
        "magic_tokens",
        "invite_links",
        "project_members",
        "tickets",
        "ticket_participants",
        "ticket_tags",
        "invite_link_projects",
    }
    _drop_all_fks_involving(*sorted(affected))

    for table in _COMPOSITE_PK_TABLES:
        _drop_constraints(table, contypes="pu")

    _drop_constraints("tags", contypes="u")

    for child, col, _parent, nullable in _FK_REMAPS:
        _finalize_fk(child, col, nullable=nullable)

    for table in _PK_TABLES:
        _finalize_pk(table)

    op.create_unique_constraint("uq_tag_project_name", "tags", ["project_id", "name"])

    op.create_primary_key(
        "project_members_pkey", "project_members", ["project_id", "user_id"]
    )
    op.create_unique_constraint(
        "uq_project_member", "project_members", ["project_id", "user_id"]
    )

    op.create_primary_key(
        "ticket_participants_pkey", "ticket_participants", ["ticket_id", "user_id"]
    )
    op.create_unique_constraint(
        "uq_ticket_participant", "ticket_participants", ["ticket_id", "user_id"]
    )

    op.create_primary_key("ticket_tags_pkey", "ticket_tags", ["ticket_id", "tag_id"])
    op.create_unique_constraint("uq_ticket_tag", "ticket_tags", ["ticket_id", "tag_id"])

    op.create_primary_key(
        "invite_link_projects_pkey",
        "invite_link_projects",
        ["invite_id", "project_id"],
    )

    for table, col in (
        ("tickets", "project_id"),
        ("tickets", "author_id"),
        ("tickets", "assignee_id"),
        ("tags", "project_id"),
        ("attachments", "comment_id"),
        ("magic_tokens", "user_id"),
        ("comments", "ticket_id"),
        ("attachments", "ticket_id"),
    ):
        existing = (
            op.get_bind()
            .execute(
                sa.text(
                    f"""
                SELECT 1 FROM pg_indexes
                WHERE tablename = '{table}' AND indexname = 'ix_{table}_{col}'
                """
                )
            )
            .first()
        )
        if not existing:
            op.create_index(f"ix_{table}_{col}", table, [col])

    op.create_foreign_key(
        "project_members_project_id_fkey",
        "project_members",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "project_members_user_id_fkey",
        "project_members",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "tickets_project_id_fkey",
        "tickets",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "tickets_author_id_fkey",
        "tickets",
        "users",
        ["author_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "tickets_assignee_id_fkey",
        "tickets",
        "users",
        ["assignee_id"],
        ["id"],
        ondelete="SET NULL",
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
        "comments_author_id_fkey",
        "comments",
        "users",
        ["author_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "tags_project_id_fkey",
        "tags",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
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
        "attachments_ticket_id_fkey",
        "attachments",
        "tickets",
        ["ticket_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "attachments_comment_id_fkey",
        "attachments",
        "comments",
        ["comment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "magic_tokens_user_id_fkey",
        "magic_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "invite_links_created_by_id_fkey",
        "invite_links",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "invite_link_projects_invite_id_fkey",
        "invite_link_projects",
        "invite_links",
        ["invite_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "invite_link_projects_project_id_fkey",
        "invite_link_projects",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    raise NotImplementedError("Irreversible: UUID PKs removed")
