from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import BenchmarkSnapshot, PortfolioSnapshot
from app.schemas.api import PortfolioView


def _pending_portfolio_snapshot(
    db: Session, *, agent_id: str, snapshot_at: datetime
) -> PortfolioSnapshot | None:
    for pending in db.new:
        if (
            isinstance(pending, PortfolioSnapshot)
            and pending.agent_id == agent_id
            and pending.snapshot_at == snapshot_at
        ):
            return pending
    return None


def _pending_benchmark_snapshot(
    db: Session, *, symbol: str, snapshot_at: datetime
) -> BenchmarkSnapshot | None:
    for pending in db.new:
        if (
            isinstance(pending, BenchmarkSnapshot)
            and pending.symbol == symbol
            and pending.snapshot_at == snapshot_at
        ):
            return pending
    return None


def store_portfolio_snapshot(
    db: Session,
    *,
    agent_id: str,
    portfolio: PortfolioView,
    snapshot_at: datetime,
) -> PortfolioSnapshot:
    snapshot = _pending_portfolio_snapshot(
        db, agent_id=agent_id, snapshot_at=snapshot_at
    )
    if snapshot is None:
        snapshot = db.scalar(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.agent_id == agent_id,
                PortfolioSnapshot.snapshot_at == snapshot_at,
            )
        )
    if snapshot is None:
        snapshot = PortfolioSnapshot(agent_id=agent_id, snapshot_at=snapshot_at)
        db.add(snapshot)

    snapshot.total_value = Decimal(str(portfolio.total_value))
    snapshot.cash = Decimal(str(portfolio.cash))
    snapshot.pnl = Decimal(str(portfolio.pnl))
    snapshot.return_pct = Decimal(str(portfolio.return_pct))
    return snapshot


def store_benchmark_snapshot(
    db: Session,
    *,
    symbol: str,
    total_value: Decimal,
    return_pct: Decimal,
    snapshot_at: datetime,
) -> BenchmarkSnapshot:
    snapshot = _pending_benchmark_snapshot(
        db, symbol=symbol, snapshot_at=snapshot_at
    )
    if snapshot is None:
        snapshot = db.scalar(
            select(BenchmarkSnapshot).where(
                BenchmarkSnapshot.symbol == symbol,
                BenchmarkSnapshot.snapshot_at == snapshot_at,
            )
        )
    if snapshot is None:
        snapshot = BenchmarkSnapshot(symbol=symbol, snapshot_at=snapshot_at)
        db.add(snapshot)

    snapshot.total_value = total_value
    snapshot.return_pct = return_pct
    return snapshot
