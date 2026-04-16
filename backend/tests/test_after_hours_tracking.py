from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import Base
from app.models.entities import (
    Agent,
    BenchmarkSnapshot,
    BenchmarkState,
    Execution,
    ExecutionSide,
    PortfolioSnapshot,
    Position,
    TradingMode,
    User,
)
from app.services.leaderboard import get_daily_change_pct
from app.services.market_data import MarketDataClient
from app.workers.snapshot_worker import SnapshotWorker


class DummyPriceFeedService:
    def __init__(self, prices: dict[str, Decimal]) -> None:
        self.prices = dict(prices)
        self.refresh_once = AsyncMock()
        self.refresh_symbols = AsyncMock()

    def snapshot(self) -> dict[str, Decimal]:
        return dict(self.prices)


class MarketDataSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MarketDataClient()

    def test_alpaca_snapshot_prefers_live_extended_hours_prices(self) -> None:
        price = self.client._extract_alpaca_equity_price(
            {
                "latestTrade": {"p": 187.42},
                "latestQuote": {"bp": 187.1, "ap": 187.3},
                "minuteBar": {"c": 186.9},
                "dailyBar": {"c": 185.0},
            }
        )

        self.assertEqual(price, Decimal("187.420000"))

    def test_alpaca_snapshot_prefers_fresher_quote_over_older_trade(self) -> None:
        price = self.client._extract_alpaca_equity_price(
            {
                "latestTrade": {
                    "p": 187.42,
                    "t": "2026-04-14T20:01:00Z",
                },
                "latestQuote": {
                    "bp": 188.0,
                    "ap": 188.4,
                    "t": "2026-04-14T20:04:00Z",
                },
                "minuteBar": {
                    "c": 187.9,
                    "t": "2026-04-14T20:02:00Z",
                },
            }
        )

        self.assertEqual(price, Decimal("188.200000"))

    def test_alpaca_snapshot_falls_back_when_symbol_is_not_trading(self) -> None:
        midpoint_price = self.client._extract_alpaca_equity_price(
            {
                "latestQuote": {"bp": 99.5, "ap": 100.5},
                "minuteBar": {"c": 98.0},
                "dailyBar": {"c": 97.0},
            }
        )
        bar_price = self.client._extract_alpaca_equity_price(
            {
                "latestQuote": {},
                "minuteBar": {},
                "dailyBar": {"c": 97.0},
                "prevDailyBar": {"c": 96.0},
            }
        )

        self.assertEqual(midpoint_price, Decimal("100.000000"))
        self.assertEqual(bar_price, Decimal("97.000000"))

    def test_get_latest_prices_uses_alpaca_only_for_equities(self) -> None:
        async def run() -> None:
            response = httpx.Response(
                200,
                json={
                    "snapshots": {
                        "AAPL": {"latestTrade": {"p": 201.25}},
                        "MSFT": {"latestQuote": {"bp": 99.0, "ap": 101.0}},
                    }
                },
            )

            with patch.object(self.client, "_has_alpaca_credentials", return_value=True):
                with patch.object(self.client, "_headers", return_value={"X": "Y"}):
                    with patch(
                        "app.services.market_data.httpx.AsyncClient.get",
                        new=AsyncMock(return_value=response),
                    ):
                        result = await self.client.get_latest_prices(["AAPL", "MSFT"])

            self.assertEqual(result.provider, "alpaca")
            self.assertEqual(
                result.prices,
                {
                    "AAPL": Decimal("201.250000"),
                    "MSFT": Decimal("100.000000"),
                },
            )

        self._run_async(run())

    def test_get_latest_prices_accepts_top_level_alpaca_snapshot_payload(self) -> None:
        async def run() -> None:
            response = httpx.Response(
                200,
                json={
                    "AAPL": {"latestTrade": {"p": 201.25}},
                    "MSFT": {"latestQuote": {"bp": 99.0, "ap": 101.0}},
                },
            )

            with patch.object(self.client, "_has_alpaca_credentials", return_value=True):
                with patch.object(self.client, "_headers", return_value={"X": "Y"}):
                    with patch(
                        "app.services.market_data.httpx.AsyncClient.get",
                        new=AsyncMock(return_value=response),
                    ):
                        result = await self.client.get_latest_prices(["AAPL", "MSFT"])

            self.assertEqual(result.provider, "alpaca")
            self.assertEqual(
                result.prices,
                {
                    "AAPL": Decimal("201.250000"),
                    "MSFT": Decimal("100.000000"),
                },
            )

        self._run_async(run())

    def _run_async(self, coroutine) -> None:
        import asyncio

        asyncio.run(coroutine)


class AfterHoursSnapshotWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.db"
        self.engine = create_engine(
            f"sqlite:///{database_path}", connect_args={"check_same_thread": False}
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_snapshot_worker_captures_after_hours_points(self) -> None:
        with self.session_factory() as db:
            user = User(
                username="after-hours-owner",
                account_api_key_hash="account",
                account_api_key_prefix="account",
            )
            db.add(user)
            db.flush()

            agent = Agent(
                user_id=user.id,
                name="Night Owl",
                api_key_hash="agent",
                api_key_prefix="agent",
                starting_cash=Decimal("10000"),
                trading_mode=TradingMode.PAPER,
            )
            db.add(agent)
            db.flush()

            db.add(
                Execution(
                    agent_id=agent.id,
                    external_order_id="buy-aapl",
                    symbol="AAPL",
                    side=ExecutionSide.BUY,
                    quantity=Decimal("1"),
                    price_per_share=Decimal("100"),
                    gross_notional=Decimal("100"),
                    fees=Decimal("0"),
                    realized_pnl=Decimal("0"),
                    executed_at=datetime(2026, 4, 15, 14, 0, tzinfo=UTC),
                )
            )
            db.add(
                Position(
                    agent_id=agent.id,
                    symbol="AAPL",
                    quantity=Decimal("1"),
                    avg_cost_basis=Decimal("100"),
                    updated_at=datetime(2026, 4, 15, 14, 0, tzinfo=UTC),
                )
            )
            db.add(
                BenchmarkState(
                    id=1,
                    symbol="SPY",
                    starting_cash=Decimal("10000"),
                    starting_price=Decimal("500"),
                    created_at=datetime(2026, 4, 15, 13, 30, tzinfo=UTC),
                )
            )
            db.commit()
            agent_id = agent.id

        price_feed_service = DummyPriceFeedService(
            {"AAPL": Decimal("125"), "SPY": Decimal("505")}
        )
        worker = SnapshotWorker(
            self.session_factory,
            price_feed_service,
            interval_minutes=2,
        )
        after_close = datetime(2026, 4, 15, 22, 4, tzinfo=UTC)

        with patch("app.workers.snapshot_worker.utc_now", return_value=after_close):
            self._run_async(worker.maybe_snapshot())

        with self.session_factory() as db:
            portfolio_snapshots = list(
                db.scalars(
                    select(PortfolioSnapshot).where(
                        PortfolioSnapshot.agent_id == agent_id
                    )
                ).all()
            )
            benchmark_snapshots = list(
                db.scalars(
                    select(BenchmarkSnapshot).where(BenchmarkSnapshot.symbol == "SPY")
                ).all()
            )

        self.assertEqual(len(portfolio_snapshots), 1)
        self.assertEqual(portfolio_snapshots[0].snapshot_at, after_close)
        self.assertEqual(float(portfolio_snapshots[0].total_value), 10025.0)
        self.assertEqual(len(benchmark_snapshots), 1)
        self.assertEqual(float(benchmark_snapshots[0].total_value), 10100.0)
        price_feed_service.refresh_symbols.assert_awaited_once_with(["AAPL", "SPY"])
        price_feed_service.refresh_once.assert_not_awaited()

    def _run_async(self, coroutine) -> None:
        import asyncio

        asyncio.run(coroutine)


class LeaderboardAfterHoursTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.db"
        self.engine = create_engine(
            f"sqlite:///{database_path}", connect_args={"check_same_thread": False}
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _seed_agent(self) -> str:
        with self.session_factory() as db:
            user = User(
                username="leaderboard-owner",
                account_api_key_hash="account",
                account_api_key_prefix="account",
            )
            db.add(user)
            db.flush()

            agent = Agent(
                user_id=user.id,
                name="Closer",
                api_key_hash="agent",
                api_key_prefix="agent",
                starting_cash=Decimal("10000"),
                trading_mode=TradingMode.PAPER,
            )
            db.add(agent)
            db.flush()
            db.commit()
            return agent.id

    def _seed_snapshots(self, agent_id: str, snapshots: list[tuple[Decimal, datetime]]) -> None:
        with self.session_factory() as db:
            db.add_all(
                [
                    PortfolioSnapshot(
                        agent_id=agent_id,
                        total_value=total_value,
                        cash=total_value,
                        pnl=total_value - Decimal("10000"),
                        return_pct=(total_value - Decimal("10000")) / Decimal("100"),
                        snapshot_at=snapshot_at,
                    )
                    for total_value, snapshot_at in snapshots
                ]
            )
            db.commit()

    def test_daily_change_uses_latest_after_hours_snapshot_before_overnight_rollover(
        self,
    ) -> None:
        agent_id = self._seed_agent()
        self._seed_snapshots(
            agent_id,
            [
                (Decimal("10000"), datetime(2026, 4, 14, 20, 0, tzinfo=UTC)),
                (Decimal("10100"), datetime(2026, 4, 15, 20, 0, tzinfo=UTC)),
                (Decimal("10200"), datetime(2026, 4, 15, 23, 30, tzinfo=UTC)),
            ],
        )

        with self.session_factory() as db:
            agent = db.get(Agent, agent_id)
            assert agent is not None
            with patch(
                "app.services.leaderboard.utc_now",
                return_value=datetime(2026, 4, 15, 23, 45, tzinfo=UTC),
            ):
                change = get_daily_change_pct(db, agent)

        self.assertEqual(change, 2.0)

    def test_daily_change_rolls_overnight_snapshots_into_next_trading_day(self) -> None:
        agent_id = self._seed_agent()
        self._seed_snapshots(
            agent_id,
            [
                (Decimal("10000"), datetime(2026, 4, 14, 20, 0, tzinfo=UTC)),
                (Decimal("10100"), datetime(2026, 4, 15, 20, 0, tzinfo=UTC)),
                (Decimal("10200"), datetime(2026, 4, 16, 0, 30, tzinfo=UTC)),
            ],
        )

        with self.session_factory() as db:
            agent = db.get(Agent, agent_id)
            assert agent is not None
            with patch(
                "app.services.leaderboard.utc_now",
                return_value=datetime(2026, 4, 16, 1, 0, tzinfo=UTC),
            ):
                change = get_daily_change_pct(db, agent)

        self.assertAlmostEqual(change, 0.9900990099009901)


if __name__ == "__main__":
    unittest.main()
