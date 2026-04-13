from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TradeIntent(APIModel):
    symbol: str
    side: Literal["buy", "sell"]
    amount_dollars: float | None = Field(default=None, gt=0)
    client_order_id: str | None = None
    sell_all: bool = False

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_amounts(self) -> "TradeIntent":
        if self.sell_all and self.side != "sell":
            raise ValueError("sell_all can only be used with sell trades.")
        if self.amount_dollars is None and not self.sell_all:
            raise ValueError("amount_dollars is required unless sell_all is true.")
        return self


class TradeSubmissionRequest(APIModel):
    trades: list[TradeIntent] = Field(min_length=1)
    rationale: str | None = None
    cycle_cost: float | None = Field(default=None, ge=0)


class TradeResult(APIModel):
    client_order_id: str
    status: str
    symbol: str
    side: str
    quantity: float | None = None
    price_per_share: float | None = None
    total: float | None = None
    rejection_reason: str | None = None


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


class TradeSubmissionResponse(APIModel):
    results: list[TradeResult]
    portfolio_after: PortfolioView


class TradeExecutionRequest(APIModel):
    symbol: str
    side: Literal["buy", "sell"]
    amount_dollars: float | None = Field(default=None, gt=0)
    client_order_id: str | None = None
    sell_all: bool = False
    rationale: str | None = None
    cycle_cost: float | None = Field(default=None, ge=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_amounts(self) -> "TradeExecutionRequest":
        if self.sell_all and self.side != "sell":
            raise ValueError("sell_all can only be used with sell trades.")
        if self.amount_dollars is None and not self.sell_all:
            raise ValueError("amount_dollars is required unless sell_all is true.")
        return self


class TradeExecutionResponse(APIModel):
    result: TradeResult
    portfolio_after: PortfolioView


class UserCreateRequest(APIModel):
    username: str = Field(min_length=3, max_length=120)
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("username is required.")
        return normalized

    @field_validator("alpaca_base_url")
    @classmethod
    def normalize_alpaca_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("alpaca_base_url is required.")
        return normalized


class UserCreateResponse(APIModel):
    user_id: str
    username: str
    alpaca_base_url: str
    is_paper: bool
    account_api_key: str | None = None
    account_api_key_prefix: str | None = None


class AgentCreateRequest(APIModel):
    user_id: str
    name: str = Field(min_length=1, max_length=255)
    starting_cash: float = Field(gt=0)
    icon_url: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_agent_name(cls, value: str) -> str:
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
    icon_url: str | None = None
    is_paper: bool


class AgentIdentity(APIModel):
    agent_id: str
    user_id: str
    name: str
    icon_url: str | None = None
    starting_cash: float
    is_paper: bool


class MockAgentCreateRequest(APIModel):
    name: str = Field(min_length=1, max_length=255)
    username: str | None = None
    starting_cash: float = Field(default=10000.0, gt=0)
    icon_url: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_mock_agent_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name is required.")
        return normalized


class MockAgentCreateResponse(APIModel):
    user_id: str
    agent_id: str
    name: str
    api_key: str
    account_api_key: str | None = None
    is_paper: bool
    username: str


class SignupRequest(UserCreateRequest):
    pass


class SignupResponse(UserCreateResponse):
    account_api_key: str
    account_api_key_prefix: str


class AccountAgentCreateRequest(APIModel):
    name: str = Field(min_length=1, max_length=255)
    starting_cash: float = Field(default=10000.0, gt=0)
    icon_url: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name is required.")
        return normalized


class AccountAgentSummary(APIModel):
    agent_id: str
    name: str
    icon_url: str | None = None
    starting_cash: float
    api_key_prefix: str
    is_paper: bool
    created_at: datetime


class AccountIdentity(APIModel):
    user_id: str
    username: str
    alpaca_base_url: str
    is_paper: bool
    account_api_key_prefix: str | None = None


class AccountOverview(APIModel):
    account: AccountIdentity
    agents: list[AccountAgentSummary]


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
    id: int
    agent_id: str
    agent_name: str
    icon_url: str | None = None
    event_type: str
    summary: str
    metadata: dict
    cost_tokens: float | None = None
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
    trade_count: int
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
    cost_tokens: float | None = None
    timestamp: datetime


class DashboardBootstrap(APIModel):
    leaderboard: LeaderboardPayload
    activity: list[ActivityItem]
    snapshots: list[SnapshotPoint]
    range: str


SnapshotRange = Literal["1D", "1W", "1M", "ALL"]
