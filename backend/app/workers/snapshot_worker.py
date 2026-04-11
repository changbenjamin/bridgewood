from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import get_settings
from app.models.entities import (
    Agent,
    BenchmarkSnapshot,
    BenchmarkState,
    PortfolioSnapshot,
)
from app.services.portfolio_engine import build_portfolio


settings = get_settings()


def is_market_hours(now: datetime | None = None) -> bool:
    current = (now or datetime.utcnow()).astimezone(ZoneInfo("America/New_York"))
    if current.weekday() >= 5:
        return False
    opening = current.replace(hour=9, minute=30, second=0, microsecond=0)
    closing = current.replace(hour=16, minute=0, second=0, microsecond=0)
    return opening <= current <= closing


class SnapshotWorker:
    def __init__(
        self, session_factory, price_feed_service, interval_minutes: int
    ) -> None:
        self.session_factory = session_factory
        self.price_feed_service = price_feed_service
        self.interval_minutes = interval_minutes
        self._task: asyncio.Task | None = None
        self._last_slot: datetime | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def run(self) -> None:
        while True:
            try:
                await self.maybe_snapshot()
            except Exception:
                pass
            await asyncio.sleep(30)

    async def maybe_snapshot(self) -> None:
        now = datetime.utcnow().replace(second=0, microsecond=0)
        slot = now - timedelta(minutes=now.minute % self.interval_minutes)
        should_capture = settings.mock_broker_mode or is_market_hours(now)
        if not should_capture or self._last_slot == slot:
            return

        if not self.price_feed_service.snapshot():
            await self.price_feed_service.refresh_once()

        prices = self.price_feed_service.snapshot()
        with self.session_factory() as db:
            for agent in db.scalars(
                select(Agent).order_by(Agent.created_at.asc())
            ).all():
                portfolio = build_portfolio(db, agent, prices)
                db.add(
                    PortfolioSnapshot(
                        agent_id=agent.id,
                        total_value=Decimal(str(portfolio.total_value)),
                        cash=Decimal(str(portfolio.cash)),
                        pnl=Decimal(str(portfolio.pnl)),
                        return_pct=Decimal(str(portfolio.return_pct)),
                        snapshot_at=slot,
                    )
                )

            benchmark_state = db.get(BenchmarkState, 1)
            if benchmark_state and benchmark_state.symbol in prices:
                current_price = prices[benchmark_state.symbol]
                starting_price = Decimal(benchmark_state.starting_price)
                total_value = Decimal(benchmark_state.starting_cash) * (
                    current_price / starting_price
                )
                return_pct = (
                    (total_value - Decimal(benchmark_state.starting_cash))
                    / Decimal(benchmark_state.starting_cash)
                ) * Decimal("100")
                db.add(
                    BenchmarkSnapshot(
                        symbol=benchmark_state.symbol,
                        total_value=total_value,
                        return_pct=return_pct,
                        snapshot_at=slot,
                    )
                )

            db.commit()
        self._last_slot = slot
