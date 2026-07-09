"""Add the 'parser' agent role (structured-output parser model assignment).

Revision ID: f3b7d82ac915
Revises: e7a2c9d51b04
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op

revision: str = "f3b7d82ac915"
down_revision: str | None = "e7a2c9d51b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE agent_role ADD VALUE IF NOT EXISTS 'parser'")


def downgrade() -> None:
    # Removing an enum value requires a type rebuild; the extra value is
    # harmless, so downgrade is a no-op.
    pass
