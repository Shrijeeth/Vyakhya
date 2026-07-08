"""projects.user_prompt + projects.figures + visual_type 'orbit.3d'.

Revision ID: d4f8a1c03b52
Revises: a1c9e4d2b7f0
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d4f8a1c03b52"
down_revision: str | None = "a1c9e4d2b7f0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("user_prompt", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("figures", JSONB(), nullable=True))
    # New visual type (PG ≥12 allows ADD VALUE in a transaction as long as the
    # same transaction doesn't USE the value).
    op.execute("ALTER TYPE visual_type ADD VALUE IF NOT EXISTS 'orbit.3d'")
    op.execute("ALTER TYPE visual_type ADD VALUE IF NOT EXISTS 'custom.html'")


def downgrade() -> None:
    op.drop_column("projects", "figures")
    op.drop_column("projects", "user_prompt")
    # PG enums can't drop values; leave 'orbit.3d' in place.
