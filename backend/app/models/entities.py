from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Enum as SqlEnum,
    ForeignKey,
    Numeric,
    String,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import UTCDateTime
from app.core.time import utc_now


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class ExecutionSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class CashAdjustmentKind(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


def uuid_str() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    account_api_key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    account_api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )

    agents: Mapped[list["Agent"]] = relationship(back_populates="user")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(500))
    trading_mode: Mapped[TradingMode] = mapped_column(
        SqlEnum(TradingMode), nullable=False, default=TradingMode.PAPER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="agents")
    executions: Mapped[list["Execution"]] = relationship(back_populates="agent")
    positions: Mapped[list["Position"]] = relationship(back_populates="agent")
    cash_adjustments: Mapped[list["CashAdjustment"]] = relationship(
        back_populates="agent"
    )

    @property
    def is_paper(self) -> bool:
        return self.trading_mode == TradingMode.PAPER


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "external_order_id",
            name="uq_executions_agent_external_order_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=False, index=True
    )
    external_order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    side: Mapped[ExecutionSide] = mapped_column(SqlEnum(ExecutionSide), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    price_per_share: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    gross_notional: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=0
    )
    executed_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False, index=True
    )

    agent: Mapped[Agent] = relationship(back_populates="executions")


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("agent_id", "symbol", name="uq_positions_agent_symbol"),
    )

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    avg_cost_basis: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )

    agent: Mapped[Agent] = relationship(back_populates="positions")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "snapshot_at",
            name="uq_portfolio_snapshots_agent_snapshot_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=False, index=True
    )
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    return_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )


class CashAdjustment(Base):
    __tablename__ = "cash_adjustments"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "external_id",
            name="uq_cash_adjustments_agent_external_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=False, index=True
    )
    kind: Mapped[CashAdjustmentKind] = mapped_column(
        SqlEnum(CashAdjustmentKind, native_enum=False), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    effective_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False, index=True
    )

    agent: Mapped[Agent] = relationship(back_populates="cash_adjustments")

    @property
    def signed_amount(self) -> Decimal:
        amount = Decimal(self.amount)
        if self.kind == CashAdjustmentKind.DEPOSIT:
            return amount
        return -amount


class BenchmarkState(Base):
    __tablename__ = "benchmark_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    starting_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )


class BenchmarkSnapshot(Base):
    __tablename__ = "benchmark_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "snapshot_at",
            name="uq_benchmark_snapshots_symbol_snapshot_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    return_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
