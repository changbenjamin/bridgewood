from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _strip_string(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


def _validate_required_name(value: str) -> str:
    if not value:
        raise ValueError("name is required.")
    return value


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
    alpaca_base_url: str | None = None
    is_paper: bool
    account_api_key: str | None = None
    account_api_key_prefix: str | None = None
    paper_trading_enabled: bool = False
    live_trading_enabled: bool = False


class AgentCreateRequest(APIModel):
    user_id: str
    name: str = Field(min_length=1, max_length=255)
    starting_cash: float = Field(gt=0)
    real_money: bool = False
    icon_url: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_agent_name(cls, value: object) -> object:
        return _strip_string(value)

    @field_validator("name")
    @classmethod
    def validate_agent_name(cls, value: str) -> str:
        return _validate_required_name(value)


class AgentCreateResponse(APIModel):
    agent_id: str
    name: str
    api_key: str
    api_key_prefix: str
    starting_cash: float
    real_money: bool = False
    icon_url: str | None = None
    is_paper: bool


class AgentIdentity(APIModel):
    agent_id: str
    user_id: str
    name: str
    icon_url: str | None = None
    starting_cash: float
    real_money: bool = False
    is_paper: bool


class MockAgentCreateRequest(APIModel):
    name: str = Field(min_length=1, max_length=255)
    username: str | None = None
    starting_cash: float = Field(default=10000.0, gt=0)
    icon_url: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_mock_agent_name(cls, value: object) -> object:
        return _strip_string(value)

    @field_validator("name")
    @classmethod
    def validate_mock_agent_name(cls, value: str) -> str:
        return _validate_required_name(value)


class MockAgentCreateResponse(APIModel):
    user_id: str
    agent_id: str
    name: str
    api_key: str
    account_api_key: str | None = None
    real_money: bool = False
    is_paper: bool
    username: str


class SignupRequest(APIModel):
    username: str = Field(min_length=3, max_length=120)
    alpaca_paper_api_key: str | None = None
    alpaca_paper_secret_key: str | None = None
    alpaca_live_api_key: str | None = None
    alpaca_live_secret_key: str | None = None

    @field_validator(
        "username",
        "alpaca_paper_api_key",
        "alpaca_paper_secret_key",
        "alpaca_live_api_key",
        "alpaca_live_secret_key",
    )
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_credential_pairs(self) -> "SignupRequest":
        has_paper_key = self.alpaca_paper_api_key is not None
        has_paper_secret = self.alpaca_paper_secret_key is not None
        has_live_key = self.alpaca_live_api_key is not None
        has_live_secret = self.alpaca_live_secret_key is not None

        if has_paper_key != has_paper_secret:
            raise ValueError(
                "alpaca_paper_api_key and alpaca_paper_secret_key must both be provided."
            )
        if has_live_key != has_live_secret:
            raise ValueError(
                "alpaca_live_api_key and alpaca_live_secret_key must both be provided."
            )
        if not (has_paper_key or has_live_key):
            raise ValueError(
                "Provide at least one Alpaca credential set: paper, live, or both."
            )
        return self


class SignupResponse(UserCreateResponse):
    account_api_key: str
    account_api_key_prefix: str


class AccountAgentCreateRequest(APIModel):
    name: str = Field(min_length=1, max_length=255)
    starting_cash: float = Field(default=10000.0, gt=0)
    real_money: bool = False
    icon_url: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip_string(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_required_name(value)


class AccountAgentRenameRequest(APIModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip_string(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_required_name(value)


class AccountAgentSummary(APIModel):
    agent_id: str
    name: str
    icon_url: str | None = None
    starting_cash: float
    api_key_prefix: str
    real_money: bool = False
    is_paper: bool
    created_at: datetime


class AccountIdentity(APIModel):
    user_id: str
    username: str
    paper_trading_enabled: bool
    live_trading_enabled: bool
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
