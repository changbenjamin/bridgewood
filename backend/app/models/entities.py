from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"


class ActivityEventType(str, Enum):
    TRADE = "trade"
    CYCLE_SUMMARY = "cycle_summary"


def uuid_str() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    account_api_key_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    account_api_key_prefix: Mapped[str | None] = mapped_column(String(16))
    alpaca_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    alpaca_secret_key: Mapped[str] = mapped_column(Text, nullable=False)
    alpaca_base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
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
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="agents")
    trades: Mapped[list["Trade"]] = relationship(back_populates="agent")
    positions: Mapped[list["Position"]] = relationship(back_populates="agent")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    side: Mapped[TradeSide] = mapped_column(SqlEnum(TradeSide), nullable=False)
    amount_dollars: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    price_per_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    filled_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    alpaca_order_id: Mapped[str | None] = mapped_column(String(128))
    client_order_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TradeStatus] = mapped_column(SqlEnum(TradeStatus), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    agent: Mapped[Agent] = relationship(back_populates="trades")


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
        DateTime, default=datetime.utcnow, nullable=False
    )

    agent: Mapped[Agent] = relationship(back_populates="positions")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=False, index=True
    )
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    return_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=False, index=True
    )
    event_type: Mapped[ActivityEventType] = mapped_column(
        SqlEnum(ActivityEventType), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    cost_tokens: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )


class BenchmarkState(Base):
    __tablename__ = "benchmark_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    starting_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class BenchmarkSnapshot(Base):
    __tablename__ = "benchmark_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    return_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
