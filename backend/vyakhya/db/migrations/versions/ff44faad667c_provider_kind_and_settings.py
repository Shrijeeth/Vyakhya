"""provider kind and settings

Revision ID: ff44faad667c
Revises: b8d46f50707c
Create Date: 2026-07-08 16:33:53.710864
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ff44faad667c"
down_revision: str | None = "b8d46f50707c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New provider_id values (TTS providers). ALTER TYPE ... ADD VALUE must run
    # outside the migration transaction — autogenerate does not detect these.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE provider_id ADD VALUE IF NOT EXISTS 'hyperframes'")
        op.execute("ALTER TYPE provider_id ADD VALUE IF NOT EXISTS 'deepgram'")

    provider_kind = postgresql.ENUM("llm", "tts", name="provider_kind")
    provider_kind.create(op.get_bind(), checkfirst=True)

    # Add kind nullable, backfill from provider (llm vs tts), then enforce NOT NULL.
    op.add_column("provider_connections", sa.Column("kind", provider_kind, nullable=True))
    op.execute(
        "UPDATE provider_connections SET kind = CASE "
        "WHEN provider::text IN ('hyperframes', 'elevenlabs', 'deepgram') "
        "THEN 'tts'::provider_kind ELSE 'llm'::provider_kind END"
    )
    op.alter_column("provider_connections", "kind", nullable=False)

    op.add_column(
        "provider_connections",
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_connections", "settings")
    op.drop_column("provider_connections", "kind")
    postgresql.ENUM(name="provider_kind").drop(op.get_bind(), checkfirst=True)
    # provider_id enum VALUEs cannot be dropped in Postgres; harmless to leave.
