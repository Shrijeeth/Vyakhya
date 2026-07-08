"""projects.paper_text — extracted PDF text stored at upload time.

Revision ID: a1c9e4d2b7f0
Revises: 853543e29367
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a1c9e4d2b7f0"
down_revision: str | None = "853543e29367"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("paper_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "paper_text")
