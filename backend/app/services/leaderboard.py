from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean, pstdev

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    Agent,
    BenchmarkSnapshot,
    BenchmarkState,
    PortfolioSnapshot,
    Trade,
    TradeSide,
    TradeStatus,
)
from app.schemas.api import LeaderboardEntry, LeaderboardPayload, SnapshotPoint
from app.services.portfolio_engine import build_portfolio


settings = get_settings()


def _benchmark_id(symbol: str) -> str:
    return f"benchmark:{symbol}"


def _benchmark_name(symbol: str) -> str:
    return (
        "S&P 500 Index"
        if symbol == settings.benchmark_symbol
        else f"{symbol} Benchmark"
    )


def get_daily_change_pct(db: Session, agent: Agent) -> float:
    cutoff = datetime.utcnow() - timedelta(days=2)
    snapshots = list(
        db.scalars(
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.agent_id == agent.id,
                PortfolioSnapshot.snapshot_at >= cutoff,
            )
            .order_by(PortfolioSnapshot.snapshot_at.asc())
        )
    )
    if len(snapshots) < 2:
        return 0.0
    grouped: dict[date, Decimal] = {}
    for snapshot in snapshots:
        grouped[snapshot.snapshot_at.date()] = Decimal(snapshot.total_value)
    values = list(grouped.values())
    if len(values) < 2 or values[-2] == 0:
        return 0.0
    return float(((values[-1] - values[-2]) / values[-2]) * Decimal("100"))


def compute_sharpe(db: Session, agent_id: str) -> float:
    snapshots = list(
        db.scalars(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.agent_id == agent_id)
            .order_by(PortfolioSnapshot.snapshot_at.asc())
        )
    )
    if len(snapshots) < 2:
        return 0.0

    closing_values: dict[date, Decimal] = {}
    for snapshot in snapshots:
        closing_values[snapshot.snapshot_at.date()] = Decimal(snapshot.total_value)

    values = list(closing_values.values())
    if len(values) < 2:
        return 0.0

    daily_returns: list[float] = []
    for index in range(1, len(values)):
        previous = values[index - 1]
        current = values[index]
        if previous == 0:
            continue
        daily_returns.append(float((current - previous) / previous))

    if len(daily_returns) < 2:
        return 0.0
    deviation = pstdev(daily_returns)
    if deviation == 0:
        return 0.0
    return mean(daily_returns) / deviation * math.sqrt(252)


def build_leaderboard_payload(
    db: Session, prices: dict[str, Decimal], *, timestamp: datetime | None = None
) -> LeaderboardPayload:
    timestamp = timestamp or datetime.utcnow()
    agents = list(db.scalars(select(Agent).order_by(Agent.created_at.asc())))
    entries: list[LeaderboardEntry] = []

    for agent in agents:
        portfolio = build_portfolio(db, agent, prices)
        max_win = db.scalar(
            select(func.max(Trade.realized_pnl)).where(
                Trade.agent_id == agent.id,
                Trade.status == TradeStatus.FILLED,
                Trade.side == TradeSide.SELL,
            )
        )
        max_loss = db.scalar(
            select(func.min(Trade.realized_pnl)).where(
                Trade.agent_id == agent.id,
                Trade.status == TradeStatus.FILLED,
                Trade.side == TradeSide.SELL,
            )
        )
        trade_count = (
            db.scalar(
                select(func.count())
                .select_from(Trade)
                .where(Trade.agent_id == agent.id)
            )
            or 0
        )
        entries.append(
            LeaderboardEntry(
                id=agent.id,
                name=f"{agent.name}{' *' if agent.is_paper else ''}",
                icon_url=agent.icon_url,
                cash=portfolio.cash,
                total_value=portfolio.total_value,
                pnl=portfolio.pnl,
                return_pct=portfolio.return_pct,
                sharpe=round(compute_sharpe(db, agent.id), 2),
                max_win=float(max_win or 0),
                max_loss=float(max_loss or 0),
                trade_count=trade_count,
                daily_change_pct=round(get_daily_change_pct(db, agent), 2),
            )
        )

    benchmark_state = db.get(BenchmarkState, 1)
    if benchmark_state and benchmark_state.symbol in prices:
        current_price = prices[benchmark_state.symbol]
        starting_price = Decimal(benchmark_state.starting_price)
        starting_cash = Decimal(benchmark_state.starting_cash)
        if starting_price > 0:
            total_value = starting_cash * (current_price / starting_price)
            pnl = total_value - starting_cash
            return_pct = (pnl / starting_cash) * Decimal("100")
            entries.append(
                LeaderboardEntry(
                    id=_benchmark_id(benchmark_state.symbol),
                    name=_benchmark_name(benchmark_state.symbol),
                    cash=0.0,
                    total_value=float(total_value),
                    pnl=float(pnl),
                    return_pct=float(return_pct),
                    sharpe=0.0,
                    max_win=0.0,
                    max_loss=0.0,
                    trade_count=0,
                    is_benchmark=True,
                    daily_change_pct=0.0,
                )
            )

    entries.sort(key=lambda entry: entry.total_value, reverse=True)
    return LeaderboardPayload(agents=entries, timestamp=timestamp)


def build_snapshot_series(db: Session, range_key: str) -> list[SnapshotPoint]:
    now = datetime.utcnow()
    lookback: datetime | None = None
    if range_key == "1D":
        lookback = now - timedelta(days=1)
    elif range_key == "1W":
        lookback = now - timedelta(weeks=1)
    elif range_key == "1M":
        lookback = now - timedelta(days=30)

    snapshots_query = select(PortfolioSnapshot, Agent).join(
        Agent, Agent.id == PortfolioSnapshot.agent_id
    )
    benchmark_query = select(BenchmarkSnapshot)
    if lookback is not None:
        snapshots_query = snapshots_query.where(
            PortfolioSnapshot.snapshot_at >= lookback
        )
        benchmark_query = benchmark_query.where(
            BenchmarkSnapshot.snapshot_at >= lookback
        )

    points: list[SnapshotPoint] = []
    for snapshot, agent in db.execute(
        snapshots_query.order_by(PortfolioSnapshot.snapshot_at.asc())
    ).all():
        points.append(
            SnapshotPoint(
                agent_id=agent.id,
                name=f"{agent.name}{' *' if agent.is_paper else ''}",
                total_value=float(snapshot.total_value),
                snapshot_at=snapshot.snapshot_at,
                icon_url=agent.icon_url,
            )
        )

    for snapshot in db.scalars(
        benchmark_query.order_by(BenchmarkSnapshot.snapshot_at.asc())
    ).all():
        points.append(
            SnapshotPoint(
                agent_id=_benchmark_id(snapshot.symbol),
                name=_benchmark_name(snapshot.symbol),
                total_value=float(snapshot.total_value),
                snapshot_at=snapshot.snapshot_at,
                is_benchmark=True,
            )
        )

    return points
