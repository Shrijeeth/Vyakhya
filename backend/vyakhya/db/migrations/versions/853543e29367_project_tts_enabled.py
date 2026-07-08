"""project tts_enabled

Revision ID: 853543e29367
Revises: ff44faad667c
Create Date: 2026-07-08 18:07:41.136103
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "853543e29367"
down_revision: str | None = "ff44faad667c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL with a server default so existing rows backfill to true.
    op.add_column(
        "projects",
        sa.Column("tts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("projects", "tts_enabled")
