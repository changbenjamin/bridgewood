"""Initial Bridgewood schema.

Revision ID: 20260413_01
Revises:
Create Date: 2026-04-13 16:10:00
"""

from __future__ import annotations

import alembic.op as op
import sqlalchemy as sa


revision = "20260413_01"
down_revision = None
branch_labels = None
depends_on = None


trading_mode_enum = sa.Enum("PAPER", "LIVE", name="tradingmode")
execution_side_enum = sa.Enum("BUY", "SELL", name="executionside")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("account_api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("account_api_key_prefix", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(
        "ix_users_account_api_key_hash",
        "users",
        ["account_api_key_hash"],
        unique=True,
    )

    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("api_key_prefix", sa.String(length=16), nullable=False),
        sa.Column("starting_cash", sa.Numeric(18, 6), nullable=False),
        sa.Column("icon_url", sa.String(length=500), nullable=True),
        sa.Column("trading_mode", trading_mode_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key_hash"),
    )

    op.create_table(
        "executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("external_order_id", sa.String(length=255), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", execution_side_enum, nullable=False),
        sa.Column("quantity", sa.Numeric(18, 9), nullable=False),
        sa.Column("price_per_share", sa.Numeric(18, 6), nullable=False),
        sa.Column("gross_notional", sa.Numeric(18, 6), nullable=False),
        sa.Column("fees", sa.Numeric(18, 6), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 6), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id",
            "external_order_id",
            name="uq_executions_agent_external_order_id",
        ),
    )
    op.create_index("ix_executions_agent_id", "executions", ["agent_id"], unique=False)
    op.create_index("ix_executions_symbol", "executions", ["symbol"], unique=False)
    op.create_index(
        "ix_executions_executed_at", "executions", ["executed_at"], unique=False
    )
    op.create_index(
        "ix_executions_created_at", "executions", ["created_at"], unique=False
    )

    op.create_table(
        "positions",
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 9), nullable=False),
        sa.Column("avg_cost_basis", sa.Numeric(18, 6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("agent_id", "symbol"),
        sa.UniqueConstraint("agent_id", "symbol", name="uq_positions_agent_symbol"),
    )

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("total_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("cash", sa.Numeric(18, 6), nullable=False),
        sa.Column("pnl", sa.Numeric(18, 6), nullable=False),
        sa.Column("return_pct", sa.Numeric(18, 6), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portfolio_snapshots_agent_id",
        "portfolio_snapshots",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_snapshots_snapshot_at",
        "portfolio_snapshots",
        ["snapshot_at"],
        unique=False,
    )

    op.create_table(
        "benchmark_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("starting_cash", sa.Numeric(18, 6), nullable=False),
        sa.Column("starting_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "benchmark_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("total_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("return_pct", sa.Numeric(18, 6), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_benchmark_snapshots_snapshot_at",
        "benchmark_snapshots",
        ["snapshot_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_benchmark_snapshots_snapshot_at", table_name="benchmark_snapshots"
    )
    op.drop_table("benchmark_snapshots")
    op.drop_table("benchmark_state")
    op.drop_index(
        "ix_portfolio_snapshots_snapshot_at", table_name="portfolio_snapshots"
    )
    op.drop_index("ix_portfolio_snapshots_agent_id", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
    op.drop_table("positions")
    op.drop_index("ix_executions_created_at", table_name="executions")
    op.drop_index("ix_executions_executed_at", table_name="executions")
    op.drop_index("ix_executions_symbol", table_name="executions")
    op.drop_index("ix_executions_agent_id", table_name="executions")
    op.drop_table("executions")
    op.drop_table("agents")
    op.drop_index("ix_users_account_api_key_hash", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        execution_side_enum.drop(bind, checkfirst=True)
        trading_mode_enum.drop(bind, checkfirst=True)
