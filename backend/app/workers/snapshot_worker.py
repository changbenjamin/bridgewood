from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.time import utc_now
from app.models.entities import Agent, BenchmarkState
from app.services.portfolio_engine import build_portfolio
from app.services.snapshot_store import (
    store_benchmark_snapshot,
    store_portfolio_snapshot,
)


logger = logging.getLogger(__name__)


class SnapshotWorker:
    def __init__(
        self, session_factory, price_feed_service, interval_minutes: int
    ) -> None:
        self.session_factory = session_factory
        self.price_feed_service = price_feed_service
        self.interval_minutes = interval_minutes
        self._task: asyncio.Task | None = None
        self._last_slot: datetime | None = None
        self.last_success_at: datetime | None = None
        self.last_error_at: datetime | None = None
        self.last_error_message: str | None = None

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

    def health_summary(self) -> dict[str, object]:
        return {
            "healthy": self.last_error_at is None,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "last_error_message": self.last_error_message,
        }

    async def run(self) -> None:
        while True:
            try:
                await self.maybe_snapshot()
            except Exception as exc:  # pragma: no cover - background safety
                self.last_error_at = utc_now()
                self.last_error_message = str(exc)
                logger.exception("Snapshot worker failed.", exc_info=exc)
            await asyncio.sleep(30)

    async def maybe_snapshot(self) -> None:
        now = utc_now().replace(second=0, microsecond=0)
        slot = now - timedelta(minutes=now.minute % self.interval_minutes)
        if self._last_slot == slot:
            return

        if not self.price_feed_service.snapshot():
            await self.price_feed_service.refresh_once()

        prices = self.price_feed_service.snapshot()
        captured = False

        with self.session_factory() as db:
            for agent in db.scalars(
                select(Agent)
                .where(Agent.is_active.is_(True))
                .order_by(Agent.created_at.asc())
            ).all():
                portfolio = build_portfolio(db, agent, prices, as_of=slot)
                store_portfolio_snapshot(
                    db,
                    agent_id=agent.id,
                    portfolio=portfolio,
                    snapshot_at=slot,
                )
                captured = True

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
                store_benchmark_snapshot(
                    db,
                    symbol=benchmark_state.symbol,
                    total_value=total_value,
                    return_pct=return_pct,
                    snapshot_at=slot,
                )
                captured = True

            if captured:
                db.commit()

        if captured:
            self._last_slot = slot
            self.last_success_at = utc_now()
            self.last_error_at = None
            self.last_error_message = None
