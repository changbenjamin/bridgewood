from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.time import normalize_utc, utc_now


SnapshotRange: TypeAlias = Literal["1D", "1W", "1M", "ALL"]
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9./_-]{0,31}$")
MAX_EXECUTION_QUANTITY = 10_000_000
MAX_EXECUTION_PRICE = 1_000_000
MAX_EXECUTION_FEES = 1_000_000
MAX_CASH_ADJUSTMENT_AMOUNT = 1_000_000_000
MAX_FUTURE_SKEW = timedelta(seconds=30)


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(APIModel):
    detail: str
    code: str
    errors: list[dict[str, Any]] | None = None


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


class AccountAgentRenameRequest(APIModel):
    name: str = Field(min_length=1, max_length=255)

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
    is_active: bool = True
    deactivated_at: datetime | None = None


class AccountAgentSummary(APIModel):
    agent_id: str
    name: str
    icon_url: str | None = None
    starting_cash: float
    api_key_prefix: str
    trading_mode: Literal["paper", "live"]
    is_active: bool
    deactivated_at: datetime | None = None
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
    is_active: bool
    deactivated_at: datetime | None = None


class AgentKeyRotationResponse(APIModel):
    agent_id: str
    name: str
    api_key: str
    api_key_prefix: str
    rotated_at: datetime


class AgentDeactivationResponse(APIModel):
    agent_id: str
    is_active: bool
    deactivated_at: datetime | None = None


class AgentResetResponse(APIModel):
    agent_id: str
    reset_at: datetime
    deleted_executions: int
    deleted_positions: int
    deleted_snapshots: int
    deleted_cash_adjustments: int


class CashAdjustmentCreateRequest(APIModel):
    kind: Literal["deposit", "withdrawal"] = "deposit"
    amount: float = Field(gt=0, le=MAX_CASH_ADJUSTMENT_AMOUNT)
    effective_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)
    external_id: str | None = Field(default=None, max_length=255)

    @field_validator("effective_at")
    @classmethod
    def normalize_effective_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        normalized = normalize_utc(value)
        if normalized > utc_now() + MAX_FUTURE_SKEW:
            raise ValueError("effective_at cannot be in the future.")
        return normalized

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("external_id")
    @classmethod
    def normalize_external_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("external_id cannot be empty.")
        return normalized


class CashAdjustmentItem(APIModel):
    id: str
    agent_id: str
    kind: Literal["deposit", "withdrawal"]
    amount: float
    signed_amount: float
    note: str | None = None
    external_id: str | None = None
    effective_at: datetime
    created_at: datetime


class ExecutionReportItem(APIModel):
    external_order_id: str = Field(min_length=1, max_length=255)
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, le=MAX_EXECUTION_QUANTITY)
    price: float = Field(gt=0, le=MAX_EXECUTION_PRICE)
    fees: float = Field(default=0, ge=0, le=MAX_EXECUTION_FEES)
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
        if not SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError(
                "symbol must contain only letters, numbers, '.', '/', '_' or '-'."
            )
        return normalized

    @field_validator("executed_at")
    @classmethod
    def normalize_executed_at(cls, value: datetime) -> datetime:
        normalized = normalize_utc(value)
        if normalized > utc_now() + MAX_FUTURE_SKEW:
            raise ValueError("executed_at cannot be in the future.")
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


class ExecutionListItem(APIModel):
    id: str
    external_order_id: str
    symbol: str
    side: str
    quantity: float
    price_per_share: float
    gross_notional: float
    fees: float
    realized_pnl: float
    executed_at: datetime
    created_at: datetime


class PositionView(APIModel):
    symbol: str
    quantity: float
    market_value: float
    avg_cost: float


class PortfolioView(APIModel):
    agent_id: str
    starting_cash: float
    net_cash_adjustments: float
    contributed_capital: float
    cash: float
    total_value: float
    pnl: float
    return_pct: float
    positions: list[PositionView]


class ExecutionReportResponse(APIModel):
    results: list[ExecutionResult]
    portfolio_after: PortfolioView


class CashAdjustmentCreateResponse(APIModel):
    status: Literal["recorded", "duplicate"]
    adjustment: CashAdjustmentItem
    portfolio_after: PortfolioView


class ExecutionPage(APIModel):
    items: list[ExecutionListItem]
    next_cursor: str | None = None


class PricesResponse(APIModel):
    prices: dict[str, float]
    as_of: datetime


class SnapshotPoint(APIModel):
    agent_id: str
    name: str
    total_value: float
    return_pct: float
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


class ActivityPage(APIModel):
    items: list[ActivityItem]
    next_cursor: str | None = None


class LeaderboardEntry(APIModel):
    id: str
    name: str
    icon_url: str | None = None
    trading_mode: Literal["paper", "live"] | None = None
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
