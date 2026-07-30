"""Hash magic_tokens.token values (sha256 hex).

Revision ID: 0008_hash_magic_tokens
Revises: 0007_account_activation
Create Date: 2026-07-30
"""

from __future__ import annotations

import hashlib
import re

import sqlalchemy as sa

from alembic import op

revision = "0008_hash_magic_tokens"
down_revision = "0007_account_activation"
branch_labels = None
depends_on = None

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, token FROM magic_tokens")).mappings().all()
    for row in rows:
        token = row["token"] or ""
        if _HEX64.fullmatch(token):
            continue
        hashed = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn.execute(
            sa.text("UPDATE magic_tokens SET token = :token WHERE id = :id"),
            {"token": hashed, "id": row["id"]},
        )


def downgrade() -> None:
    pass
