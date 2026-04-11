from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.models.entities import BenchmarkState, Position, User
from app.schemas.api import LeaderboardPayload
from app.services.alpaca_client import AlpacaCredentials, get_broker_gateway
from app.services.broadcaster import ConnectionManager
from app.services.leaderboard import build_leaderboard_payload
from app.services.security import decrypt_secret


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
        self.gateway = get_broker_gateway()
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

    async def refresh_once(self) -> LeaderboardPayload | None:
        with self.session_factory() as db:
            symbols = {
                position.symbol for position in db.scalars(select(Position)).all()
            }
            benchmark_state = db.get(BenchmarkState, 1)
            if benchmark_state:
                symbols.add(benchmark_state.symbol)
            symbols.add(self.settings.benchmark_symbol)
            if not symbols:
                return None

            credentials = self._get_any_credentials(db)
            if hasattr(self.gateway, "advance_prices"):
                maybe_prices = await self.gateway.advance_prices(sorted(symbols))
                if maybe_prices:
                    self.prices.update(maybe_prices)

            latest = await self.gateway.get_latest_prices(credentials, sorted(symbols))
            self.prices.update(latest)
            self.last_updated_at = datetime.utcnow()
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

    def _get_any_credentials(self, db) -> AlpacaCredentials | None:
        user = db.scalar(select(User).order_by(User.created_at.asc()))
        if user is None:
            return None
        return AlpacaCredentials(
            api_key=decrypt_secret(user.alpaca_api_key),
            secret_key=decrypt_secret(user.alpaca_secret_key),
            base_url=user.alpaca_base_url,
        )
