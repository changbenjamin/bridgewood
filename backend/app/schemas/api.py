from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


SnapshotRange: TypeAlias = Literal["1D", "1W", "1M", "ALL"]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SignupRequest(APIModel):
    username: str = Field(min_length=3, max_length=120)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("username is required.")
        return normalized


class SignupResponse(APIModel):
    user_id: str
    username: str
    account_api_key: str
    account_api_key_prefix: str


class AccountAgentCreateRequest(APIModel):
    name: str = Field(min_length=1, max_length=255)
    starting_cash: float = Field(default=10000.0, gt=0)
    trading_mode: Literal["paper", "live"] = "paper"
    icon_url: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name is required.")
        return normalized


class AgentCreateResponse(APIModel):
    agent_id: str
    name: str
    api_key: str
    api_key_prefix: str
    starting_cash: float
    trading_mode: Literal["paper", "live"]
    icon_url: str | None = None


class AccountAgentSummary(APIModel):
    agent_id: str
    name: str
    icon_url: str | None = None
    starting_cash: float
    api_key_prefix: str
    trading_mode: Literal["paper", "live"]
    created_at: datetime


class AccountIdentity(APIModel):
    user_id: str
    username: str
    account_api_key_prefix: str


class AccountOverview(APIModel):
    account: AccountIdentity
    agents: list[AccountAgentSummary]


class AgentIdentity(APIModel):
    agent_id: str
    user_id: str
    name: str
    icon_url: str | None = None
    starting_cash: float
    trading_mode: Literal["paper", "live"]


class ExecutionReportItem(APIModel):
    external_order_id: str = Field(min_length=1, max_length=255)
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fees: float = Field(default=0, ge=0)
    executed_at: datetime

    @field_validator("external_order_id")
    @classmethod
    def normalize_external_order_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("external_order_id is required.")
        return normalized

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol is required.")
        return normalized


class ExecutionReportRequest(APIModel):
    executions: list[ExecutionReportItem] = Field(min_length=1)


class ExecutionResult(APIModel):
    external_order_id: str
    status: Literal["recorded", "duplicate"]
    execution_id: str | None = None
    symbol: str
    side: str
    quantity: float
    price_per_share: float
    gross_notional: float
    fees: float
    executed_at: datetime


class PositionView(APIModel):
    symbol: str
    quantity: float
    market_value: float
    avg_cost: float


class PortfolioView(APIModel):
    agent_id: str
    cash: float
    total_value: float
    pnl: float
    return_pct: float
    positions: list[PositionView]


class ExecutionReportResponse(APIModel):
    results: list[ExecutionResult]
    portfolio_after: PortfolioView


class PricesResponse(APIModel):
    prices: dict[str, float]
    as_of: datetime


class SnapshotPoint(APIModel):
    agent_id: str
    name: str
    total_value: float
    snapshot_at: datetime
    is_benchmark: bool = False
    icon_url: str | None = None


class ActivityItem(APIModel):
    id: str
    agent_id: str
    agent_name: str
    icon_url: str | None = None
    event_type: str
    summary: str
    metadata: dict
    created_at: datetime


class LeaderboardEntry(APIModel):
    id: str
    name: str
    icon_url: str | None = None
    cash: float
    total_value: float
    pnl: float
    return_pct: float
    sharpe: float
    max_win: float
    max_loss: float
    execution_count: int
    is_benchmark: bool = False
    daily_change_pct: float = 0.0


class LeaderboardPayload(APIModel):
    type: str = "leaderboard_update"
    agents: list[LeaderboardEntry]
    timestamp: datetime


class ActivityPayload(APIModel):
    type: str = "activity"
    agent_id: str
    agent_name: str
    icon_url: str | None = None
    summary: str
    timestamp: datetime


class DashboardBootstrap(APIModel):
    leaderboard: LeaderboardPayload
    activity: list[ActivityItem]
    snapshots: list[SnapshotPoint]
    range: SnapshotRange
