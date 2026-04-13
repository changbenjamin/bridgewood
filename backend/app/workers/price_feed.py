from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.models.entities import Position
from app.schemas.api import LeaderboardPayload
from app.services.broadcaster import ConnectionManager
from app.services.leaderboard import build_leaderboard_payload
from app.services.market_data import MarketDataClient, MarketDataError


class PriceFeedService:
    def __init__(
        self,
        session_factory,
        connection_manager: ConnectionManager,
        refresh_seconds: int,
    ) -> None:
        self.session_factory = session_factory
        self.connection_manager = connection_manager
        self.refresh_seconds = refresh_seconds
        self.market_data = MarketDataClient()
        self.prices: dict[str, Decimal] = {}
        self.last_updated_at: datetime = datetime.utcnow()
        self._task: asyncio.Task | None = None
        self.settings = get_settings()

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

    def snapshot(self) -> dict[str, Decimal]:
        return dict(self.prices)

    def as_float_map(self) -> dict[str, float]:
        return {symbol: float(price) for symbol, price in self.prices.items()}

    async def refresh_symbols(self, symbols: list[str]) -> dict[str, Decimal]:
        try:
            latest = await self.market_data.get_latest_prices(symbols)
        except (MarketDataError, Exception):
            return {}

        if latest:
            self.prices.update(latest)
            self.last_updated_at = datetime.utcnow()
        return latest

    async def refresh_once(self) -> LeaderboardPayload:
        with self.session_factory() as db:
            symbols = {
                position.symbol for position in db.scalars(select(Position)).all()
            }
            symbols.add(self.settings.benchmark_symbol)

        await self.refresh_symbols(sorted(symbols))

        with self.session_factory() as db:
            payload = build_leaderboard_payload(
                db, self.prices, timestamp=self.last_updated_at
            )

        await self.connection_manager.broadcast_json(payload.model_dump(mode="json"))
        return payload

    async def run(self) -> None:
        while True:
            try:
                await self.refresh_once()
            except Exception:
                pass
            await asyncio.sleep(self.refresh_seconds)
