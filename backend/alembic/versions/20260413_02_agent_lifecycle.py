"""Add agent lifecycle fields.

Revision ID: 20260413_02
Revises: 20260413_01
Create Date: 2026-04-13 16:20:00
"""

from __future__ import annotations

import alembic.op as op
import sqlalchemy as sa


revision = "20260413_02"
down_revision = "20260413_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "agents",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "deactivated_at")
    op.drop_column("agents", "is_active")
