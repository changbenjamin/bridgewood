from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.time import utc_now
from app.models.entities import Agent, Position
from app.schemas.api import LeaderboardPayload
from app.services.broadcaster import ConnectionManager
from app.services.leaderboard import build_leaderboard_payload
from app.services.market_data import (
    MarketDataClient,
    MarketDataError,
    MarketDataResult,
)


logger = logging.getLogger(__name__)


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
        self.last_updated_at: datetime = utc_now()
        self.last_success_at: datetime | None = None
        self.last_error_at: datetime | None = None
        self.last_error_message: str | None = None
        self.last_provider: str | None = None
        self.consecutive_failures = 0
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

    def _record_success(self, provider: str | None) -> None:
        self.last_updated_at = utc_now()
        self.last_success_at = self.last_updated_at
        self.last_error_at = None
        self.last_error_message = None
        self.last_provider = provider
        self.consecutive_failures = 0

    def _record_error(self, exc: Exception) -> None:
        self.last_error_at = utc_now()
        self.last_error_message = str(exc)
        self.consecutive_failures += 1

    def health_summary(self) -> dict[str, object]:
        alpaca_configured = bool(
            self.settings.alpaca_api_key and self.settings.alpaca_secret_key
        )
        age_seconds = None
        healthy = self.last_success_at is not None
        if self.last_success_at is not None:
            age_seconds = (utc_now() - self.last_success_at).total_seconds()
        if self.last_success_at and self.last_error_at:
            healthy = self.last_success_at >= self.last_error_at
        if healthy and self.last_success_at is not None:
            if age_seconds is not None and age_seconds > max(
                60, self.refresh_seconds * 4
            ):
                healthy = False

        return {
            "configured": alpaca_configured,
            "alpaca_configured": alpaca_configured,
            "healthy": healthy,
            "provider": self.last_provider,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "last_error_message": self.last_error_message,
            "last_updated_at": self.last_updated_at,
            "stale_seconds": age_seconds,
            "consecutive_failures": self.consecutive_failures,
        }

    async def refresh_symbols(self, symbols: list[str]) -> dict[str, Decimal]:
        try:
            result: MarketDataResult = await self.market_data.get_latest_prices(symbols)
        except (MarketDataError, Exception) as exc:
            self._record_error(exc)
            logger.exception(
                "Market data refresh failed for symbols: %s", symbols, exc_info=exc
            )
            return {}

        latest = result.prices
        if latest:
            self.prices.update(latest)
            self._record_success(result.provider)
        return latest

    async def refresh_once(self) -> LeaderboardPayload:
        with self.session_factory() as db:
            symbols = {
                position.symbol
                for position in db.scalars(
                    select(Position)
                    .join(Agent, Agent.id == Position.agent_id)
                    .where(Agent.is_active.is_(True))
                ).all()
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
            except Exception as exc:  # pragma: no cover - background safety
                self._record_error(exc)
                logger.exception("Price feed loop failed.", exc_info=exc)
            await asyncio.sleep(self.refresh_seconds)
