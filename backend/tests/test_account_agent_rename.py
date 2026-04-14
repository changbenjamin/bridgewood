from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routes import router
from app.core.errors import register_exception_handlers
from app.db.session import Base, get_db
from app.models.entities import Agent, TradingMode, User
from app.services.security import generate_account_api_key, hash_api_key


class DummyConnectionManager:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def broadcast_json(self, payload: dict) -> None:
        self.payloads.append(payload)


class DummyPriceFeedService:
    def __init__(self) -> None:
        self.prices: dict[str, Decimal] = {}

    def snapshot(self) -> dict[str, Decimal]:
        return dict(self.prices)


class AccountAgentRenameTests(unittest.TestCase):
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

    def _account_headers(self, account_api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {account_api_key}"}

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

    def _create_agent(self, user_id: str, name: str = "Original Name") -> Agent:
        agent = Agent(
            user_id=user_id,
            name=name,
            api_key_hash=hash_api_key(f"agent-{uuid4()}"),
            api_key_prefix=f"agent-{uuid4().hex[:4]}",
            starting_cash=Decimal("10000"),
            trading_mode=TradingMode.PAPER,
        )
        with self.session_factory() as db:
            db.add(agent)
            db.commit()
            db.refresh(agent)
        return agent

    def test_rename_agent_success(self) -> None:
        owner, account_api_key = self._create_user("owner")
        agent = self._create_agent(owner.id)

        response = self.client.patch(
            f"/v1/account/agents/{agent.id}",
            headers=self._account_headers(account_api_key),
            json={"name": "  Renamed Agent  "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Renamed Agent")

        with self.session_factory() as db:
            updated = db.get(Agent, agent.id)
            assert updated is not None
            self.assertEqual(updated.name, "Renamed Agent")

        broadcasts = self.app.state.connection_manager.payloads
        self.assertEqual(len(broadcasts), 1)
        self.assertEqual(broadcasts[0]["type"], "leaderboard_update")
        self.assertIn(
            "Renamed Agent *",
            [entry["name"] for entry in broadcasts[0]["agents"]],
        )

    def test_rename_agent_rejects_invalid_names(self) -> None:
        owner, account_api_key = self._create_user("owner")
        agent = self._create_agent(owner.id)

        for name in ("   ", "x" * 256):
            with self.subTest(name=name):
                response = self.client.patch(
                    f"/v1/account/agents/{agent.id}",
                    headers=self._account_headers(account_api_key),
                    json={"name": name},
                )
                self.assertEqual(response.status_code, 422)

        with self.session_factory() as db:
            unchanged = db.get(Agent, agent.id)
            assert unchanged is not None
            self.assertEqual(unchanged.name, "Original Name")

        self.assertEqual(self.app.state.connection_manager.payloads, [])

    def test_rename_agent_returns_404_for_missing_agent(self) -> None:
        _, account_api_key = self._create_user("owner")

        response = self.client.patch(
            f"/v1/account/agents/{uuid4()}",
            headers=self._account_headers(account_api_key),
            json={"name": "Renamed Agent"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Agent not found.")
        self.assertEqual(self.app.state.connection_manager.payloads, [])

    def test_rename_agent_returns_404_for_other_accounts_agent(self) -> None:
        owner, owner_api_key = self._create_user("owner")
        other_user, _ = self._create_user("other")
        agent = self._create_agent(other_user.id)

        response = self.client.patch(
            f"/v1/account/agents/{agent.id}",
            headers=self._account_headers(owner_api_key),
            json={"name": "Renamed Agent"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Agent not found.")
        with self.session_factory() as db:
            unchanged = db.get(Agent, agent.id)
            assert unchanged is not None
            self.assertEqual(unchanged.name, "Original Name")

        self.assertEqual(self.app.state.connection_manager.payloads, [])


if __name__ == "__main__":
    unittest.main()
