from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routes import router
from app.core.errors import register_exception_handlers
from app.db.session import Base, get_db
from app.models.entities import (
    Agent,
    BenchmarkSnapshot,
    PortfolioSnapshot,
    TradingMode,
    User,
)
from app.services.security import generate_account_api_key, hash_api_key
from app.services.snapshot_store import store_benchmark_snapshot, store_portfolio_snapshot


class DummyConnectionManager:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def broadcast_json(self, payload: dict) -> None:
        self.payloads.append(payload)


class DummyPriceFeedService:
    def __init__(self) -> None:
        self.prices: dict[str, Decimal] = {
            "AAPL": Decimal("100.00"),
            "SPY": Decimal("500.00"),
        }
        self.last_updated_at = datetime(2026, 4, 14, 15, 32, tzinfo=UTC)
        self.market_data = self

    def snapshot(self) -> dict[str, Decimal]:
        return dict(self.prices)

    async def refresh_symbols(self, symbols: list[str]) -> dict[str, Decimal]:
        latest = {
            symbol: self.prices.get(symbol, Decimal("100.00"))
            for symbol in symbols
        }
        self.prices.update(latest)
        self.last_updated_at = datetime(2026, 4, 14, 15, 32, tzinfo=UTC)
        return latest

    async def get_equity_bars(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        timeframe: str,
    ):
        del symbol, start, end, timeframe
        return []


class DummyRateLimiter:
    async def check(self, scope: str, key: str, *, detail: str) -> None:
        del scope, key, detail


class ExecutionSnapshotTests(unittest.TestCase):
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

        self.app = FastAPI()
        self.app.include_router(router, prefix="/v1")
        register_exception_handlers(self.app)
        self.app.state.connection_manager = DummyConnectionManager()
        self.app.state.price_feed_service = DummyPriceFeedService()
        self.app.state.rate_limiter = DummyRateLimiter()

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _agent_headers(self, agent_api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {agent_api_key}"}

    def _create_user(self, username: str) -> tuple[User, str]:
        account_api_key = generate_account_api_key()
        user = User(
            username=f"{username}-{uuid4().hex[:8]}",
            account_api_key_hash=hash_api_key(account_api_key),
            account_api_key_prefix=account_api_key[:10],
        )
        with self.session_factory() as db:
            db.add(user)
            db.commit()
            db.refresh(user)
        return user, account_api_key

    def _create_agent(
        self, user_id: str, name: str = "TradingBot"
    ) -> tuple[Agent, str]:
        agent_api_key = f"bgw_test_{uuid4().hex}"
        agent = Agent(
            user_id=user_id,
            name=name,
            api_key_hash=hash_api_key(agent_api_key),
            api_key_prefix=agent_api_key[:10],
            starting_cash=Decimal("10000"),
            trading_mode=TradingMode.PAPER,
        )
        with self.session_factory() as db:
            db.add(agent)
            db.commit()
            db.refresh(agent)
        return agent, agent_api_key

    def test_reporting_execution_persists_snapshot_and_broadcasts_leaderboard(
        self,
    ) -> None:
        owner, _ = self._create_user("owner")
        agent, agent_api_key = self._create_agent(owner.id)

        response = self.client.post(
            "/v1/executions",
            headers=self._agent_headers(agent_api_key),
            json={
                "executions": [
                    {
                        "external_order_id": "order-1",
                        "symbol": "AAPL",
                        "side": "buy",
                        "quantity": 5,
                        "price": 100,
                        "fees": 1,
                        "executed_at": "2026-04-14T15:31:00Z",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["portfolio_after"]["cash"], 9499.0)
        self.assertEqual(payload["portfolio_after"]["total_value"], 9999.0)

        with self.session_factory() as db:
            snapshots = list(
                db.scalars(
                    select(PortfolioSnapshot).where(
                        PortfolioSnapshot.agent_id == agent.id
                    )
                ).all()
            )
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(
                snapshots[0].snapshot_at,
                self.app.state.price_feed_service.last_updated_at,
            )
            self.assertEqual(float(snapshots[0].total_value), 9999.0)

        broadcasts = self.app.state.connection_manager.payloads
        self.assertEqual(
            [payload["type"] for payload in broadcasts],
            ["leaderboard_update", "activity"],
        )

        dashboard = self.client.get("/v1/dashboard?range=ALL")
        self.assertEqual(dashboard.status_code, 200)
        agent_snapshots = [
            point
            for point in dashboard.json()["snapshots"]
            if point["agent_id"] == agent.id
        ]
        self.assertEqual(len(agent_snapshots), 1)
        self.assertEqual(agent_snapshots[0]["total_value"], 9999.0)

    def test_snapshot_writes_are_idempotent_per_timestamp(self) -> None:
        owner, _ = self._create_user("owner")
        agent, _ = self._create_agent(owner.id)
        snapshot_at = datetime(2026, 4, 14, 16, 0, tzinfo=UTC)

        with self.session_factory() as db:
            store_portfolio_snapshot(
                db,
                agent_id=agent.id,
                portfolio=SimpleNamespace(
                    total_value=10010.0,
                    cash=5000.0,
                    pnl=10.0,
                    return_pct=0.1,
                ),
                snapshot_at=snapshot_at,
            )
            store_portfolio_snapshot(
                db,
                agent_id=agent.id,
                portfolio=SimpleNamespace(
                    total_value=10025.0,
                    cash=4900.0,
                    pnl=25.0,
                    return_pct=0.25,
                ),
                snapshot_at=snapshot_at,
            )
            store_benchmark_snapshot(
                db,
                symbol="SPY",
                total_value=Decimal("10100"),
                return_pct=Decimal("1.00"),
                snapshot_at=snapshot_at,
            )
            store_benchmark_snapshot(
                db,
                symbol="SPY",
                total_value=Decimal("10150"),
                return_pct=Decimal("1.50"),
                snapshot_at=snapshot_at,
            )
            db.commit()

            portfolio_snapshots = list(
                db.scalars(
                    select(PortfolioSnapshot).where(
                        PortfolioSnapshot.agent_id == agent.id
                    )
                ).all()
            )
            benchmark_snapshots = list(
                db.scalars(
                    select(BenchmarkSnapshot).where(BenchmarkSnapshot.symbol == "SPY")
                ).all()
            )

        self.assertEqual(len(portfolio_snapshots), 1)
        self.assertEqual(float(portfolio_snapshots[0].total_value), 10025.0)
        self.assertEqual(len(benchmark_snapshots), 1)
        self.assertEqual(float(benchmark_snapshots[0].total_value), 10150.0)


if __name__ == "__main__":
    unittest.main()
