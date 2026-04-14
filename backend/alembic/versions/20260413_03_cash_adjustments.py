"""Add cash adjustment ledger.

Revision ID: 20260413_03
Revises: 20260413_02
Create Date: 2026-04-13 18:40:00
"""

from __future__ import annotations

import alembic.op as op
import sqlalchemy as sa


revision = "20260413_03"
down_revision = "20260413_02"
branch_labels = None
depends_on = None


cash_adjustment_kind_enum = sa.Enum(
    "DEPOSIT",
    "WITHDRAWAL",
    name="cashadjustmentkind",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "cash_adjustments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("kind", cash_adjustment_kind_enum, nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id",
            "external_id",
            name="uq_cash_adjustments_agent_external_id",
        ),
    )
    op.create_index(
        "ix_cash_adjustments_agent_id",
        "cash_adjustments",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_cash_adjustments_effective_at",
        "cash_adjustments",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        "ix_cash_adjustments_created_at",
        "cash_adjustments",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cash_adjustments_created_at", table_name="cash_adjustments")
    op.drop_index("ix_cash_adjustments_effective_at", table_name="cash_adjustments")
    op.drop_index("ix_cash_adjustments_agent_id", table_name="cash_adjustments")
    op.drop_table("cash_adjustments")
