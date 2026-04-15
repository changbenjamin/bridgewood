from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean, pstdev
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utc_now
from app.models.entities import (
    Agent,
    BenchmarkSnapshot,
    BenchmarkState,
    CashAdjustment,
    Execution,
    ExecutionSide,
    PortfolioSnapshot,
)
from app.schemas.api import LeaderboardEntry, LeaderboardPayload, SnapshotPoint
from app.services.portfolio_engine import (
    build_portfolio,
    cash_adjustment_total,
    money,
    time_weighted_return_series,
)


settings = get_settings()
EASTERN_TZ = ZoneInfo("America/New_York")


def _benchmark_id(symbol: str) -> str:
    return f"benchmark:{symbol}"


def _benchmark_name(symbol: str) -> str:
    return (
        "S&P 500 Index"
        if symbol == settings.benchmark_symbol
        else f"{symbol} Benchmark"
    )


def _display_name(agent: Agent) -> str:
    return f"{agent.name}{' *' if agent.is_paper else ''}"


def _snapshot_trading_day(snapshot_at: datetime) -> date:
    eastern = snapshot_at.astimezone(EASTERN_TZ)
    trading_day = eastern.date()
    if eastern.hour >= 20:
        return trading_day + timedelta(days=1)
    return trading_day


def get_snapshot_lookback(range_key: str) -> datetime | None:
    now = utc_now()
    if range_key == "1D":
        return now - timedelta(days=1)
    if range_key == "1W":
        return now - timedelta(weeks=1)
    if range_key == "1M":
        return now - timedelta(days=30)
    return None


def get_daily_change_pct(db: Session, agent: Agent) -> float:
    cutoff = utc_now() - timedelta(days=7)
    snapshots = list(
        db.scalars(
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.agent_id == agent.id,
                PortfolioSnapshot.snapshot_at >= cutoff,
            )
            .order_by(PortfolioSnapshot.snapshot_at.asc(), PortfolioSnapshot.id.asc())
        )
    )
    if len(snapshots) < 2:
        return 0.0
    grouped: dict[date, PortfolioSnapshot] = {}
    for snapshot in snapshots:
        grouped[_snapshot_trading_day(snapshot.snapshot_at)] = snapshot
    closing_snapshots = list(grouped.values())
    if len(closing_snapshots) < 2:
        return 0.0
    previous = closing_snapshots[-2]
    current = closing_snapshots[-1]
    previous_value = Decimal(previous.total_value)
    if previous_value <= 0:
        return 0.0
    net_flow = cash_adjustment_total(
        db,
        agent.id,
        start_after=previous.snapshot_at,
        end_at=current.snapshot_at,
    )
    return float(
        ((Decimal(current.total_value) - previous_value - net_flow) / previous_value)
        * Decimal("100")
    )


def compute_sharpe(db: Session, agent_id: str) -> float:
    snapshots = list(
        db.scalars(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.agent_id == agent_id)
            .order_by(PortfolioSnapshot.snapshot_at.asc(), PortfolioSnapshot.id.asc())
        )
    )
    if len(snapshots) < 2:
        return 0.0

    closing_snapshots: dict[date, PortfolioSnapshot] = {}
    for snapshot in snapshots:
        closing_snapshots[_snapshot_trading_day(snapshot.snapshot_at)] = snapshot

    values = list(closing_snapshots.values())
    if len(values) < 2:
        return 0.0

    daily_returns: list[float] = []
    for index in range(1, len(values)):
        previous = values[index - 1]
        current = values[index]
        previous_value = Decimal(previous.total_value)
        if previous_value <= 0:
            continue
        net_flow = cash_adjustment_total(
            db,
            agent_id,
            start_after=previous.snapshot_at,
            end_at=current.snapshot_at,
        )
        daily_returns.append(
            float(
                (Decimal(current.total_value) - previous_value - net_flow)
                / previous_value
            )
        )

    if len(daily_returns) < 2:
        return 0.0
    deviation = pstdev(daily_returns)
    if deviation == 0:
        return 0.0
    return mean(daily_returns) / deviation * math.sqrt(252)


def build_leaderboard_payload(
    db: Session, prices: dict[str, Decimal], *, timestamp: datetime | None = None
) -> LeaderboardPayload:
    timestamp = timestamp or utc_now()
    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.is_active.is_(True))
            .order_by(Agent.created_at.asc())
        )
    )
    entries: list[LeaderboardEntry] = []

    for agent in agents:
        portfolio = build_portfolio(db, agent, prices, as_of=timestamp)
        max_win = db.scalar(
            select(func.max(Execution.realized_pnl)).where(
                Execution.agent_id == agent.id,
                Execution.side == ExecutionSide.SELL,
            )
        )
        max_loss = db.scalar(
            select(func.min(Execution.realized_pnl)).where(
                Execution.agent_id == agent.id,
                Execution.side == ExecutionSide.SELL,
            )
        )
        execution_count = (
            db.scalar(
                select(func.count())
                .select_from(Execution)
                .where(Execution.agent_id == agent.id)
            )
            or 0
        )
        entries.append(
            LeaderboardEntry(
                id=agent.id,
                name=_display_name(agent),
                icon_url=agent.icon_url,
                trading_mode=agent.trading_mode.value,
                cash=portfolio.cash,
                total_value=portfolio.total_value,
                pnl=portfolio.pnl,
                return_pct=portfolio.return_pct,
                sharpe=round(compute_sharpe(db, agent.id), 2),
                max_win=float(max_win or 0),
                max_loss=float(max_loss or 0),
                execution_count=execution_count,
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
                    trading_mode=None,
                    total_value=float(total_value),
                    pnl=float(pnl),
                    return_pct=float(return_pct),
                    sharpe=0.0,
                    max_win=0.0,
                    max_loss=0.0,
                    execution_count=0,
                    is_benchmark=True,
                    daily_change_pct=0.0,
                )
            )

    entries.sort(key=lambda entry: (entry.return_pct, entry.total_value), reverse=True)
    return LeaderboardPayload(agents=entries, timestamp=timestamp)


def _build_agent_snapshot_points(
    db: Session, agent: Agent, snapshots: list[PortfolioSnapshot]
) -> list[SnapshotPoint]:
    if not snapshots:
        return []

    adjustments = list(
        db.scalars(
            select(CashAdjustment)
            .where(
                CashAdjustment.agent_id == agent.id,
                CashAdjustment.effective_at <= snapshots[-1].snapshot_at,
            )
            .order_by(
                CashAdjustment.effective_at.asc(),
                CashAdjustment.created_at.asc(),
                CashAdjustment.id.asc(),
            )
        ).all()
    )
    valuations = [
        (snapshot.snapshot_at, money(Decimal(snapshot.total_value)))
        for snapshot in snapshots
    ]
    return_by_timestamp = {
        snapshot_at: return_pct
        for snapshot_at, return_pct in time_weighted_return_series(
            agent, valuations, adjustments
        )
    }

    return [
        SnapshotPoint(
            agent_id=agent.id,
            name=_display_name(agent),
            total_value=float(snapshot.total_value),
            return_pct=float(
                return_by_timestamp.get(snapshot.snapshot_at, Decimal("0"))
            ),
            snapshot_at=snapshot.snapshot_at,
            icon_url=agent.icon_url,
        )
        for snapshot in snapshots
    ]


def build_snapshot_series(db: Session, range_key: str) -> list[SnapshotPoint]:
    lookback = get_snapshot_lookback(range_key)

    snapshots_query = (
        select(PortfolioSnapshot, Agent)
        .join(Agent, Agent.id == PortfolioSnapshot.agent_id)
        .where(Agent.is_active.is_(True))
    )
    benchmark_query = select(BenchmarkSnapshot)
    if lookback is not None:
        benchmark_query = benchmark_query.where(
            BenchmarkSnapshot.snapshot_at >= lookback
        )

    points: list[SnapshotPoint] = []
    snapshots_by_agent: dict[str, dict[datetime, PortfolioSnapshot]] = {}
    agents_by_id: dict[str, Agent] = {}
    for snapshot, agent in db.execute(
        snapshots_query.order_by(
            PortfolioSnapshot.snapshot_at.asc(), PortfolioSnapshot.id.asc()
        )
    ).all():
        snapshots_by_agent.setdefault(agent.id, {})[snapshot.snapshot_at] = snapshot
        agents_by_id[agent.id] = agent

    for agent_id, snapshot_map in snapshots_by_agent.items():
        snapshots = list(snapshot_map.values())
        points.extend(
            _build_agent_snapshot_points(db, agents_by_id[agent_id], snapshots)
        )

    if lookback is not None:
        points = [point for point in points if point.snapshot_at >= lookback]

    benchmark_points: dict[datetime, BenchmarkSnapshot] = {}
    for snapshot in db.scalars(
        benchmark_query.order_by(
            BenchmarkSnapshot.snapshot_at.asc(), BenchmarkSnapshot.id.asc()
        )
    ).all():
        benchmark_points[snapshot.snapshot_at] = snapshot

    for snapshot in benchmark_points.values():
        points.append(
            SnapshotPoint(
                agent_id=_benchmark_id(snapshot.symbol),
                name=_benchmark_name(snapshot.symbol),
                total_value=float(snapshot.total_value),
                return_pct=float(snapshot.return_pct),
                snapshot_at=snapshot.snapshot_at,
                is_benchmark=True,
            )
        )

    points.sort(key=lambda point: point.snapshot_at)
    return points
