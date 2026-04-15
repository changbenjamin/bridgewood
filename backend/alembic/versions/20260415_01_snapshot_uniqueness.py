"""Deduplicate and protect snapshot timestamps.

Revision ID: 20260415_01
Revises: 20260413_03
Create Date: 2026-04-15 03:55:00
"""

from __future__ import annotations

import alembic.op as op


revision = "20260415_01"
down_revision = "20260413_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM portfolio_snapshots
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM portfolio_snapshots
            GROUP BY agent_id, snapshot_at
        )
        """
    )
    op.execute(
        """
        DELETE FROM benchmark_snapshots
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM benchmark_snapshots
            GROUP BY symbol, snapshot_at
        )
        """
    )

    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.create_unique_constraint(
            "uq_portfolio_snapshots_agent_snapshot_at",
            ["agent_id", "snapshot_at"],
        )

    with op.batch_alter_table("benchmark_snapshots") as batch_op:
        batch_op.create_unique_constraint(
            "uq_benchmark_snapshots_symbol_snapshot_at",
            ["symbol", "snapshot_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("benchmark_snapshots") as batch_op:
        batch_op.drop_constraint(
            "uq_benchmark_snapshots_symbol_snapshot_at", type_="unique"
        )

    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.drop_constraint(
            "uq_portfolio_snapshots_agent_snapshot_at", type_="unique"
        )
