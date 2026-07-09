"""agent_settings singleton + custom provider enum values

Revision ID: e7a2c9d51b04
Revises: d4f8a1c03b52
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e7a2c9d51b04"
down_revision: str | None = "d4f8a1c03b52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_id ADD VALUE IF NOT EXISTS 'custom'")
    op.execute("ALTER TYPE provider_id ADD VALUE IF NOT EXISTS 'custom_tts'")
    op.create_table(
        "agent_settings",
        sa.Column("id", sa.Boolean(), primary_key=True, default=True),
        sa.Column("verifier_max_rounds", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("visual_max_rounds", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("visual_stall_rounds", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("length_fit_rounds", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id", name="ck_agent_settings_singleton"),
        sa.CheckConstraint("verifier_max_rounds BETWEEN 1 AND 10", name="ck_verifier_rounds"),
        sa.CheckConstraint("visual_max_rounds BETWEEN 1 AND 20", name="ck_visual_rounds"),
        sa.CheckConstraint("visual_stall_rounds BETWEEN 1 AND 5", name="ck_visual_stall"),
        sa.CheckConstraint("length_fit_rounds BETWEEN 0 AND 5", name="ck_fit_rounds"),
    )


def downgrade() -> None:
    op.drop_table("agent_settings")
