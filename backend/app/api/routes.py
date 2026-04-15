from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_account_user, get_current_agent
from app.core.config import get_settings
from app.core.errors import BridgewoodError
from app.core.pagination import PageCursor, decode_cursor, encode_cursor
from app.core.time import utc_now
from app.db.session import get_db
from app.models.entities import (
    Agent,
    BenchmarkState,
    CashAdjustment,
    CashAdjustmentKind,
    Execution,
    ExecutionSide,
    PortfolioSnapshot,
    Position,
    TradingMode,
    User,
)
from app.schemas.api import (
    AccountAgentCreateRequest,
    AccountAgentRenameRequest,
    AccountAgentSummary,
    AccountIdentity,
    AccountOverview,
    ActivityItem,
    ActivityPage,
    ActivityPayload,
    CashAdjustmentCreateRequest,
    CashAdjustmentCreateResponse,
    CashAdjustmentItem,
    AgentCreateResponse,
    AgentDeactivationResponse,
    AgentIdentity,
    AgentKeyRotationResponse,
    AgentResetResponse,
    DashboardBootstrap,
    ExecutionListItem,
    ExecutionPage,
    ExecutionReportRequest,
    ExecutionReportResponse,
    ExecutionResult,
    LeaderboardPayload,
    PortfolioView,
    PricesResponse,
    SignupRequest,
    SignupResponse,
    SnapshotPoint,
    SnapshotRange,
)
from app.services.leaderboard import (
    build_leaderboard_payload,
    build_snapshot_series,
    get_snapshot_lookback,
)
from app.services.market_data import MarketDataError
from app.services.portfolio_engine import (
    apply_execution_to_position,
    build_portfolio,
    cash_adjustment_total,
    gross_notional,
    money,
    notional,
    price_value,
    quantity_value,
    signed_cash_adjustment_amount,
)
from app.services.snapshot_store import store_portfolio_snapshot
from app.services.security import (
    generate_account_api_key,
    generate_agent_api_key,
    hash_api_key,
)


router = APIRouter()
settings = get_settings()


def _display_name(agent: Agent) -> str:
    return f"{agent.name}{' *' if agent.is_paper else ''}"


def _benchmark_id(symbol: str) -> str:
    return f"benchmark:{symbol}"


def _benchmark_name(symbol: str) -> str:
    return (
        "S&P 500 Index"
        if symbol == settings.benchmark_symbol
        else f"{symbol} Benchmark"
    )


def _benchmark_timeframe(range_key: SnapshotRange) -> str:
    if range_key == "1D":
        return "5Min"
    if range_key == "1W":
        return "30Min"
    return "1Day"


def _format_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        return text.rstrip("0").rstrip(".")
    return text


def _active_agent_ids(db: Session) -> list[str]:
    return list(
        db.scalars(select(Agent.id).where(Agent.is_active.is_(True)).order_by(Agent.id))
    )


def _position_symbols_for_agents(db: Session, agent_ids: list[str]) -> list[str]:
    if not agent_ids:
        return []
    return list(
        db.scalars(
            select(Position.symbol)
            .where(Position.agent_id.in_(agent_ids))
            .distinct()
            .order_by(Position.symbol.asc())
        )
    )


async def _get_prices_for_agents(
    request: Request,
    db: Session,
    *,
    agent_ids: list[str],
    include_benchmark: bool = False,
) -> dict[str, Decimal]:
    price_feed = request.app.state.price_feed_service
    cached = price_feed.snapshot()
    missing = [
        symbol
        for symbol in _position_symbols_for_agents(db, agent_ids)
        if symbol not in cached
    ]
    if include_benchmark and settings.benchmark_symbol not in cached:
        missing.append(settings.benchmark_symbol)
    if missing:
        latest = await price_feed.refresh_symbols(sorted(set(missing)))
        cached.update(latest)
    elif not cached and include_benchmark:
        await price_feed.refresh_symbols([settings.benchmark_symbol])
        cached = price_feed.snapshot()
    return cached


def _build_execution_summary(agent: Agent, execution: Execution) -> str:
    action = "Bought" if execution.side == ExecutionSide.BUY else "Sold"
    quantity = _format_decimal(Decimal(execution.quantity))
    price = Decimal(execution.price_per_share).quantize(Decimal("0.01"))
    return f"{action} {quantity} {execution.symbol} @ ${price}"


def _build_execution_metadata(execution: Execution) -> dict[str, str | float]:
    return {
        "external_order_id": execution.external_order_id,
        "symbol": execution.symbol,
        "side": execution.side.value,
        "quantity": float(execution.quantity),
        "price_per_share": float(execution.price_per_share),
        "gross_notional": float(execution.gross_notional),
        "fees": float(execution.fees),
        "realized_pnl": float(execution.realized_pnl),
        "executed_at": execution.executed_at.isoformat(),
    }


def _build_account_identity(user: User) -> AccountIdentity:
    return AccountIdentity(
        user_id=user.id,
        username=user.username,
        account_api_key_prefix=user.account_api_key_prefix,
    )


def _build_account_agent_summary(agent: Agent) -> AccountAgentSummary:
    return AccountAgentSummary(
        agent_id=agent.id,
        name=agent.name,
        icon_url=agent.icon_url,
        starting_cash=float(agent.starting_cash),
        api_key_prefix=agent.api_key_prefix,
        trading_mode=agent.trading_mode.value,
        is_active=agent.is_active,
        deactivated_at=agent.deactivated_at,
        created_at=agent.created_at,
    )


def _build_agent_identity(agent: Agent) -> AgentIdentity:
    return AgentIdentity(
        agent_id=agent.id,
        user_id=agent.user_id,
        name=agent.name,
        icon_url=agent.icon_url,
        starting_cash=float(agent.starting_cash),
        trading_mode=agent.trading_mode.value,
        is_active=agent.is_active,
        deactivated_at=agent.deactivated_at,
    )


def _build_cash_adjustment_item(adjustment: CashAdjustment) -> CashAdjustmentItem:
    return CashAdjustmentItem(
        id=adjustment.id,
        agent_id=adjustment.agent_id,
        kind=adjustment.kind.value,
        amount=float(adjustment.amount),
        signed_amount=float(adjustment.signed_amount),
        note=adjustment.note,
        external_id=adjustment.external_id,
        effective_at=adjustment.effective_at,
        created_at=adjustment.created_at,
    )


def _build_execution_result(
    execution: Execution, *, status_value: Literal["recorded", "duplicate"]
) -> ExecutionResult:
    return ExecutionResult(
        external_order_id=execution.external_order_id,
        status=status_value,
        execution_id=execution.id,
        symbol=execution.symbol,
        side=execution.side.value,
        quantity=float(execution.quantity),
        price_per_share=float(execution.price_per_share),
        gross_notional=float(execution.gross_notional),
        fees=float(execution.fees),
        executed_at=execution.executed_at,
    )


def _build_execution_item(execution: Execution) -> ExecutionListItem:
    return ExecutionListItem(
        id=execution.id,
        external_order_id=execution.external_order_id,
        symbol=execution.symbol,
        side=execution.side.value,
        quantity=float(execution.quantity),
        price_per_share=float(execution.price_per_share),
        gross_notional=float(execution.gross_notional),
        fees=float(execution.fees),
        realized_pnl=float(execution.realized_pnl),
        executed_at=execution.executed_at,
        created_at=execution.created_at,
    )


def _build_activity_item(execution: Execution, agent: Agent) -> ActivityItem:
    return ActivityItem(
        id=execution.id,
        agent_id=agent.id,
        agent_name=_display_name(agent),
        icon_url=agent.icon_url,
        event_type="execution",
        summary=_build_execution_summary(agent, execution),
        metadata=_build_execution_metadata(execution),
        created_at=execution.executed_at,
    )


def _build_activity_payload(execution: Execution, agent: Agent) -> ActivityPayload:
    return ActivityPayload(
        agent_id=agent.id,
        agent_name=_display_name(agent),
        icon_url=agent.icon_url,
        summary=_build_execution_summary(agent, execution),
        timestamp=execution.executed_at,
    )


def _create_user_record(*, db: Session, username: str) -> tuple[User, str]:
    account_api_key = generate_account_api_key()
    user = User(
        username=username,
        account_api_key_hash=hash_api_key(account_api_key),
        account_api_key_prefix=account_api_key[:10],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, account_api_key


def _create_agent_record(
    *,
    db: Session,
    user: User,
    name: str,
    starting_cash: float,
    trading_mode: TradingMode,
    icon_url: str | None,
) -> tuple[Agent, str]:
    api_key = generate_agent_api_key()
    agent = Agent(
        user_id=user.id,
        name=name,
        api_key_hash=hash_api_key(api_key),
        api_key_prefix=api_key[:10],
        starting_cash=Decimal(str(starting_cash)),
        icon_url=icon_url,
        trading_mode=trading_mode,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent, api_key


def _agent_for_account(db: Session, *, account: User, agent_id: str) -> Agent:
    agent = db.scalar(
        select(Agent).where(Agent.user_id == account.id, Agent.id == agent_id)
    )
    if agent is None:
        raise BridgewoodError(
            status_code=404,
            detail="Agent not found.",
            code="AGENT_NOT_FOUND",
        )
    return agent


async def _build_live_portfolio(
    request: Request, db: Session, *, agent: Agent
) -> PortfolioView:
    prices = await _get_prices_for_agents(request, db, agent_ids=[agent.id])
    return build_portfolio(
        db,
        agent,
        prices,
        as_of=request.app.state.price_feed_service.last_updated_at,
    )


def _snapshot_timestamp(request: Request, *, has_prices: bool) -> datetime:
    if has_prices:
        return request.app.state.price_feed_service.last_updated_at
    return utc_now()


def _store_live_portfolio_snapshot(
    db: Session,
    *,
    agent: Agent,
    portfolio: PortfolioView,
    snapshot_at: datetime,
) -> None:
    store_portfolio_snapshot(
        db,
        agent_id=agent.id,
        portfolio=portfolio,
        snapshot_at=snapshot_at,
    )


def _execution_cursor_filter(cursor: PageCursor):
    return or_(
        Execution.executed_at < cursor.executed_at,
        and_(
            Execution.executed_at == cursor.executed_at,
            Execution.created_at < cursor.created_at,
        ),
        and_(
            Execution.executed_at == cursor.executed_at,
            Execution.created_at == cursor.created_at,
            Execution.id < cursor.row_id,
        ),
    )


def _paginate_activity(
    db: Session, *, limit: int, cursor: str | None = None
) -> ActivityPage:
    query = (
        select(Execution, Agent)
        .join(Agent, Agent.id == Execution.agent_id)
        .where(Agent.is_active.is_(True))
        .order_by(
            Execution.executed_at.desc(),
            Execution.created_at.desc(),
            Execution.id.desc(),
        )
    )
    if cursor:
        query = query.where(_execution_cursor_filter(decode_cursor(cursor)))

    rows = list(db.execute(query.limit(limit + 1)).all())
    page_rows = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page_rows:
        execution, _agent = page_rows[-1]
        next_cursor = encode_cursor(
            executed_at=execution.executed_at,
            created_at=execution.created_at,
            row_id=execution.id,
        )

    return ActivityPage(
        items=[
            _build_activity_item(execution, agent) for execution, agent in page_rows
        ],
        next_cursor=next_cursor,
    )


def _paginate_executions(
    db: Session, *, agent_id: str, limit: int, cursor: str | None = None
) -> ExecutionPage:
    query = (
        select(Execution)
        .where(Execution.agent_id == agent_id)
        .order_by(
            Execution.executed_at.desc(),
            Execution.created_at.desc(),
            Execution.id.desc(),
        )
    )
    if cursor:
        query = query.where(_execution_cursor_filter(decode_cursor(cursor)))

    rows = list(db.scalars(query.limit(limit + 1)).all())
    page_rows = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page_rows:
        execution = page_rows[-1]
        next_cursor = encode_cursor(
            executed_at=execution.executed_at,
            created_at=execution.created_at,
            row_id=execution.id,
        )

    return ExecutionPage(
        items=[_build_execution_item(execution) for execution in page_rows],
        next_cursor=next_cursor,
    )


def _merge_snapshot_points(
    points: list[SnapshotPoint], additions: list[SnapshotPoint]
) -> list[SnapshotPoint]:
    merged: dict[tuple[str, datetime], SnapshotPoint] = {
        (point.agent_id, point.snapshot_at): point for point in points
    }
    for point in additions:
        merged[(point.agent_id, point.snapshot_at)] = point
    return sorted(merged.values(), key=lambda point: point.snapshot_at)


async def _ensure_benchmark_snapshots(
    request: Request,
    db: Session,
    *,
    range_key: SnapshotRange,
    snapshots: list[SnapshotPoint],
    leaderboard: LeaderboardPayload | None = None,
) -> list[SnapshotPoint]:
    benchmark_points = [point for point in snapshots if point.is_benchmark]
    if len(benchmark_points) >= 2:
        return snapshots

    state = db.get(BenchmarkState, 1)
    if state is None:
        return snapshots

    start_at = state.created_at
    lookback = get_snapshot_lookback(range_key)
    if lookback is not None and lookback > start_at:
        start_at = lookback
    end_at = utc_now()

    additions: list[SnapshotPoint] = [
        SnapshotPoint(
            agent_id=_benchmark_id(state.symbol),
            name=_benchmark_name(state.symbol),
            total_value=float(state.starting_cash),
            return_pct=0.0,
            snapshot_at=start_at,
            is_benchmark=True,
        )
    ]

    bars = []
    try:
        bars = await request.app.state.price_feed_service.market_data.get_equity_bars(
            state.symbol,
            start=start_at,
            end=end_at,
            timeframe=_benchmark_timeframe(range_key),
        )
    except MarketDataError:
        bars = []

    starting_cash = Decimal(state.starting_cash)
    starting_price = Decimal(state.starting_price)
    if starting_price > 0:
        for bar in bars:
            total_value = starting_cash * (bar.close / starting_price)
            return_pct = ((total_value - starting_cash) / starting_cash) * Decimal(
                "100"
            )
            additions.append(
                SnapshotPoint(
                    agent_id=_benchmark_id(state.symbol),
                    name=_benchmark_name(state.symbol),
                    total_value=float(total_value),
                    return_pct=float(return_pct),
                    snapshot_at=bar.timestamp,
                    is_benchmark=True,
                )
            )

    if leaderboard is not None:
        benchmark_entry = next(
            (entry for entry in leaderboard.agents if entry.is_benchmark), None
        )
        if benchmark_entry is not None:
            additions.append(
                SnapshotPoint(
                    agent_id=benchmark_entry.id,
                    name=benchmark_entry.name,
                    total_value=benchmark_entry.total_value,
                    return_pct=benchmark_entry.return_pct,
                    snapshot_at=leaderboard.timestamp,
                    is_benchmark=True,
                    icon_url=benchmark_entry.icon_url,
                )
            )
    elif (
        state.symbol in request.app.state.price_feed_service.snapshot()
        and starting_price > 0
    ):
        current_price = request.app.state.price_feed_service.snapshot()[state.symbol]
        total_value = starting_cash * (current_price / starting_price)
        additions.append(
            SnapshotPoint(
                agent_id=_benchmark_id(state.symbol),
                name=_benchmark_name(state.symbol),
                total_value=float(total_value),
                return_pct=float(
                    ((total_value - starting_cash) / starting_cash) * Decimal("100")
                ),
                snapshot_at=request.app.state.price_feed_service.last_updated_at,
                is_benchmark=True,
            )
        )

    return _merge_snapshot_points(snapshots, additions)


async def _ensure_benchmark_initialized(request: Request, db: Session) -> None:
    state = db.get(BenchmarkState, 1)
    if state is not None:
        return

    price_feed = request.app.state.price_feed_service
    if settings.benchmark_symbol not in price_feed.snapshot():
        await price_feed.refresh_symbols([settings.benchmark_symbol])

    prices = price_feed.snapshot()
    if settings.benchmark_symbol not in prices:
        return

    db.add(
        BenchmarkState(
            id=1,
            symbol=settings.benchmark_symbol,
            starting_cash=Decimal(str(settings.benchmark_starting_cash)),
            starting_price=prices[settings.benchmark_symbol],
        )
    )
    db.commit()


async def _broadcast_cached_leaderboard(request: Request, db: Session) -> None:
    prices = await _get_prices_for_agents(
        request,
        db,
        agent_ids=_active_agent_ids(db),
        include_benchmark=True,
    )
    timestamp = (
        request.app.state.price_feed_service.last_updated_at if prices else utc_now()
    )
    payload = build_leaderboard_payload(db, prices, timestamp=timestamp)
    await request.app.state.connection_manager.broadcast_json(
        payload.model_dump(mode="json")
    )


async def _apply_rate_limit(
    request: Request, *, scope: str, key: str, detail: str
) -> None:
    await request.app.state.rate_limiter.check(scope, key, detail=detail)


@router.get("/health")
async def healthcheck(request: Request) -> dict[str, object]:
    price_feed_health = request.app.state.price_feed_service.health_summary()
    snapshot_health = request.app.state.snapshot_worker.health_summary()
    healthy = bool(price_feed_health["healthy"]) and bool(snapshot_health["healthy"])
    return {
        "status": "ok" if healthy else "degraded",
        "market_data": price_feed_health,
        "snapshots": snapshot_health,
    }


@router.post(
    "/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED
)
async def signup(
    payload: SignupRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SignupResponse:
    client_host = request.client.host if request.client else "unknown"
    await _apply_rate_limit(
        request,
        scope="signup",
        key=client_host,
        detail="Too many signup attempts. Please try again soon.",
    )

    if db.scalar(select(User).where(User.username == payload.username)):
        raise BridgewoodError(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
            code="USERNAME_EXISTS",
        )

    user, account_api_key = _create_user_record(db=db, username=payload.username)
    await _ensure_benchmark_initialized(request, db)
    return SignupResponse(
        user_id=user.id,
        username=user.username,
        account_api_key=account_api_key,
        account_api_key_prefix=user.account_api_key_prefix,
    )


@router.get("/account/me", response_model=AccountOverview)
async def get_account_me(
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> AccountOverview:
    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.user_id == account.id)
            .order_by(Agent.created_at.asc())
        )
    )
    return AccountOverview(
        account=_build_account_identity(account),
        agents=[_build_account_agent_summary(agent) for agent in agents],
    )


@router.get("/account/agents", response_model=list[AccountAgentSummary])
async def get_account_agents(
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> list[AccountAgentSummary]:
    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.user_id == account.id)
            .order_by(Agent.created_at.asc())
        )
    )
    return [_build_account_agent_summary(agent) for agent in agents]


@router.post(
    "/account/agents",
    response_model=AgentCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_account_agent(
    payload: AccountAgentCreateRequest,
    request: Request,
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> AgentCreateResponse:
    await _apply_rate_limit(
        request,
        scope="agent_create",
        key=account.id,
        detail="Too many agent creation requests. Please try again soon.",
    )

    agent, api_key = _create_agent_record(
        db=db,
        user=account,
        name=payload.name,
        starting_cash=payload.starting_cash,
        trading_mode=TradingMode(payload.trading_mode),
        icon_url=payload.icon_url,
    )
    await _ensure_benchmark_initialized(request, db)
    return AgentCreateResponse(
        agent_id=agent.id,
        name=agent.name,
        api_key=api_key,
        api_key_prefix=agent.api_key_prefix,
        starting_cash=float(agent.starting_cash),
        trading_mode=agent.trading_mode.value,
        icon_url=agent.icon_url,
        is_active=agent.is_active,
        deactivated_at=agent.deactivated_at,
    )


@router.patch("/account/agents/{agent_id}", response_model=AccountAgentSummary)
async def rename_account_agent(
    agent_id: str,
    payload: AccountAgentRenameRequest,
    request: Request,
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> AccountAgentSummary:
    agent = _agent_for_account(db, account=account, agent_id=agent_id)
    agent.name = payload.name
    db.commit()
    db.refresh(agent)
    await _broadcast_cached_leaderboard(request, db)
    return _build_account_agent_summary(agent)


@router.delete("/account/agents/{agent_id}", response_model=AccountAgentSummary)
async def delete_account_agent(
    agent_id: str,
    request: Request,
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> AccountAgentSummary:
    agent = _agent_for_account(db, account=account, agent_id=agent_id)
    deleted_summary = _build_account_agent_summary(agent)

    db.execute(delete(CashAdjustment).where(CashAdjustment.agent_id == agent.id))
    db.execute(delete(Execution).where(Execution.agent_id == agent.id))
    db.execute(delete(Position).where(Position.agent_id == agent.id))
    db.execute(delete(PortfolioSnapshot).where(PortfolioSnapshot.agent_id == agent.id))
    db.delete(agent)
    db.commit()

    await _broadcast_cached_leaderboard(request, db)
    return deleted_summary


@router.get(
    "/account/agents/{agent_id}/cash-adjustments",
    response_model=list[CashAdjustmentItem],
)
async def get_agent_cash_adjustments(
    agent_id: str,
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> list[CashAdjustmentItem]:
    agent = _agent_for_account(db, account=account, agent_id=agent_id)
    adjustments = list(
        db.scalars(
            select(CashAdjustment)
            .where(CashAdjustment.agent_id == agent.id)
            .order_by(
                CashAdjustment.effective_at.desc(),
                CashAdjustment.created_at.desc(),
                CashAdjustment.id.desc(),
            )
        ).all()
    )
    return [_build_cash_adjustment_item(adjustment) for adjustment in adjustments]


@router.post(
    "/account/agents/{agent_id}/cash-adjustments",
    response_model=CashAdjustmentCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_cash_adjustment(
    agent_id: str,
    payload: CashAdjustmentCreateRequest,
    request: Request,
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> CashAdjustmentCreateResponse:
    agent = _agent_for_account(db, account=account, agent_id=agent_id)

    if payload.external_id:
        existing = db.scalar(
            select(CashAdjustment).where(
                CashAdjustment.agent_id == agent.id,
                CashAdjustment.external_id == payload.external_id,
            )
        )
        if existing is not None:
            portfolio = await _build_live_portfolio(request, db, agent=agent)
            return CashAdjustmentCreateResponse(
                status="duplicate",
                adjustment=_build_cash_adjustment_item(existing),
                portfolio_after=portfolio,
            )

    effective_at = payload.effective_at or utc_now()
    if effective_at < agent.created_at:
        raise BridgewoodError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="effective_at cannot be earlier than the agent creation time.",
            code="INVALID_EFFECTIVE_AT",
        )

    kind = CashAdjustmentKind(payload.kind)
    amount = money(Decimal(str(payload.amount)))
    signed_amount = signed_cash_adjustment_amount(kind, amount)
    capital_after_adjustment = (
        Decimal(agent.starting_cash)
        + cash_adjustment_total(db, agent.id, end_at=effective_at)
        + signed_amount
    )
    if capital_after_adjustment <= 0:
        raise BridgewoodError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cash adjustment would reduce contributed capital to zero or below.",
            code="INVALID_CASH_ADJUSTMENT",
        )

    adjustment = CashAdjustment(
        agent_id=agent.id,
        kind=kind,
        amount=amount,
        note=payload.note,
        external_id=payload.external_id,
        effective_at=effective_at,
    )
    db.add(adjustment)
    db.commit()
    db.refresh(adjustment)

    portfolio = await _build_live_portfolio(request, db, agent=agent)
    snapshot_at = _snapshot_timestamp(
        request, has_prices=bool(request.app.state.price_feed_service.snapshot())
    )
    _store_live_portfolio_snapshot(
        db,
        agent=agent,
        portfolio=portfolio,
        snapshot_at=snapshot_at,
    )
    db.commit()
    await _broadcast_cached_leaderboard(request, db)
    return CashAdjustmentCreateResponse(
        status="recorded",
        adjustment=_build_cash_adjustment_item(adjustment),
        portfolio_after=portfolio,
    )


@router.post(
    "/account/agents/{agent_id}/rotate-key",
    response_model=AgentKeyRotationResponse,
)
async def rotate_agent_key(
    agent_id: str,
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> AgentKeyRotationResponse:
    agent = _agent_for_account(db, account=account, agent_id=agent_id)
    api_key = generate_agent_api_key()
    rotated_at = utc_now()

    agent.api_key_hash = hash_api_key(api_key)
    agent.api_key_prefix = api_key[:10]
    db.commit()
    db.refresh(agent)

    return AgentKeyRotationResponse(
        agent_id=agent.id,
        name=agent.name,
        api_key=api_key,
        api_key_prefix=agent.api_key_prefix,
        rotated_at=rotated_at,
    )


@router.post(
    "/account/agents/{agent_id}/reset",
    response_model=AgentResetResponse,
)
async def reset_agent(
    agent_id: str,
    request: Request,
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> AgentResetResponse:
    agent = _agent_for_account(db, account=account, agent_id=agent_id)
    deleted_cash_adjustments = (
        db.execute(
            delete(CashAdjustment).where(CashAdjustment.agent_id == agent.id)
        ).rowcount
        or 0
    )
    deleted_executions = (
        db.execute(delete(Execution).where(Execution.agent_id == agent.id)).rowcount
        or 0
    )
    deleted_positions = (
        db.execute(delete(Position).where(Position.agent_id == agent.id)).rowcount or 0
    )
    deleted_snapshots = (
        db.execute(
            delete(PortfolioSnapshot).where(PortfolioSnapshot.agent_id == agent.id)
        ).rowcount
        or 0
    )
    db.commit()

    await _broadcast_cached_leaderboard(request, db)
    return AgentResetResponse(
        agent_id=agent.id,
        reset_at=utc_now(),
        deleted_executions=deleted_executions,
        deleted_positions=deleted_positions,
        deleted_snapshots=deleted_snapshots,
        deleted_cash_adjustments=deleted_cash_adjustments,
    )


@router.post(
    "/account/agents/{agent_id}/deactivate",
    response_model=AgentDeactivationResponse,
)
async def deactivate_agent(
    agent_id: str,
    request: Request,
    account: User = Depends(get_current_account_user),
    db: Session = Depends(get_db),
) -> AgentDeactivationResponse:
    agent = _agent_for_account(db, account=account, agent_id=agent_id)
    if agent.is_active:
        agent.is_active = False
        agent.deactivated_at = utc_now()
        db.commit()
        db.refresh(agent)
        await _broadcast_cached_leaderboard(request, db)

    return AgentDeactivationResponse(
        agent_id=agent.id,
        is_active=agent.is_active,
        deactivated_at=agent.deactivated_at,
    )


@router.get("/me", response_model=AgentIdentity)
async def get_me(agent: Agent = Depends(get_current_agent)) -> AgentIdentity:
    return _build_agent_identity(agent)


@router.get("/portfolio", response_model=PortfolioView)
async def get_portfolio(
    request: Request,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
) -> PortfolioView:
    return await _build_live_portfolio(request, db, agent=agent)


@router.get("/executions", response_model=ExecutionPage)
async def get_executions(
    limit: int = Query(
        default=settings.execution_page_size, ge=1, le=settings.max_page_size
    ),
    cursor: str | None = Query(default=None),
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
) -> ExecutionPage:
    return _paginate_executions(db, agent_id=agent.id, limit=limit, cursor=cursor)


@router.get("/prices", response_model=PricesResponse)
async def get_prices(
    request: Request,
    symbols: str = Query(...),
    agent: Agent = Depends(get_current_agent),
) -> PricesResponse:
    del agent

    symbol_list = [
        symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()
    ]
    price_feed = request.app.state.price_feed_service
    cached = price_feed.snapshot()
    missing = [symbol for symbol in symbol_list if symbol not in cached]
    if missing:
        latest = await price_feed.refresh_symbols(missing)
        cached.update(latest)
    return PricesResponse(
        prices={
            symbol: float(cached[symbol]) for symbol in symbol_list if symbol in cached
        },
        as_of=price_feed.last_updated_at,
    )


@router.post("/executions", response_model=ExecutionReportResponse)
async def report_executions(
    payload: ExecutionReportRequest,
    request: Request,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
) -> ExecutionReportResponse:
    await _apply_rate_limit(
        request,
        scope="execution_report",
        key=agent.id,
        detail="Too many execution reports. Please try again soon.",
    )

    seen_external_ids: set[str] = set()
    result_by_external_id: dict[str, ExecutionResult] = {}

    for execution in payload.executions:
        if execution.external_order_id in seen_external_ids:
            raise BridgewoodError(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Duplicate external_order_id in request.",
                code="DUPLICATE_EXTERNAL_ORDER_ID",
            )
        seen_external_ids.add(execution.external_order_id)

    external_ids = [execution.external_order_id for execution in payload.executions]
    existing_models = list(
        db.scalars(
            select(Execution).where(
                Execution.agent_id == agent.id,
                Execution.external_order_id.in_(external_ids),
            )
        )
    )
    existing_by_external_id = {
        execution.external_order_id: execution for execution in existing_models
    }

    new_executions = []
    for execution in payload.executions:
        existing = existing_by_external_id.get(execution.external_order_id)
        if existing is not None:
            result_by_external_id[execution.external_order_id] = (
                _build_execution_result(existing, status_value="duplicate")
            )
            continue
        new_executions.append(execution)

    recorded_models: list[Execution] = []
    new_executions.sort(key=lambda item: item.executed_at)

    try:
        for execution in new_executions:
            quantity = quantity_value(Decimal(str(execution.quantity)))
            price = price_value(Decimal(str(execution.price)))
            fees = notional(Decimal(str(execution.fees)))
            side = ExecutionSide(execution.side)

            execution_model = Execution(
                agent_id=agent.id,
                external_order_id=execution.external_order_id,
                symbol=execution.symbol,
                side=side,
                quantity=quantity,
                price_per_share=price,
                gross_notional=gross_notional(quantity, price),
                fees=fees,
                realized_pnl=apply_execution_to_position(
                    db,
                    agent_id=agent.id,
                    symbol=execution.symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    fees=fees,
                ),
                executed_at=execution.executed_at,
            )
            db.add(execution_model)
            db.flush()
            recorded_models.append(execution_model)
            result_by_external_id[execution.external_order_id] = (
                _build_execution_result(execution_model, status_value="recorded")
            )

        db.commit()
    except BridgewoodError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    prices = await _get_prices_for_agents(request, db, agent_ids=[agent.id])
    snapshot_at = _snapshot_timestamp(request, has_prices=bool(prices))
    portfolio = build_portfolio(
        db,
        agent,
        prices,
        as_of=snapshot_at,
    )
    _store_live_portfolio_snapshot(
        db,
        agent=agent,
        portfolio=portfolio,
        snapshot_at=snapshot_at,
    )
    db.commit()

    await _broadcast_cached_leaderboard(request, db)

    for execution in recorded_models:
        activity_payload = _build_activity_payload(execution, agent)
        await request.app.state.connection_manager.broadcast_json(
            activity_payload.model_dump(mode="json")
        )

    ordered_results = [
        result_by_external_id[execution.external_order_id]
        for execution in payload.executions
    ]
    return ExecutionReportResponse(results=ordered_results, portfolio_after=portfolio)


@router.get("/leaderboard", response_model=LeaderboardPayload)
async def get_leaderboard(
    request: Request, db: Session = Depends(get_db)
) -> LeaderboardPayload:
    await _ensure_benchmark_initialized(request, db)
    prices = await _get_prices_for_agents(
        request,
        db,
        agent_ids=_active_agent_ids(db),
        include_benchmark=True,
    )
    return build_leaderboard_payload(db, prices)


@router.get("/activity", response_model=ActivityPage)
async def get_activity(
    limit: int = Query(
        default=settings.activity_page_size, ge=1, le=settings.max_page_size
    ),
    cursor: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ActivityPage:
    return _paginate_activity(db, limit=limit, cursor=cursor)


@router.get("/snapshots", response_model=list[SnapshotPoint])
async def get_snapshots(
    request: Request,
    range: SnapshotRange = Query(default="1D"),
    db: Session = Depends(get_db),
) -> list[SnapshotPoint]:
    await _ensure_benchmark_initialized(request, db)
    await _get_prices_for_agents(
        request,
        db,
        agent_ids=[],
        include_benchmark=True,
    )
    snapshots = build_snapshot_series(db, range)
    return await _ensure_benchmark_snapshots(
        request,
        db,
        range_key=range,
        snapshots=snapshots,
    )


@router.get("/dashboard", response_model=DashboardBootstrap)
async def get_dashboard(
    request: Request,
    range: SnapshotRange = Query(default="1D"),
    db: Session = Depends(get_db),
) -> DashboardBootstrap:
    await _ensure_benchmark_initialized(request, db)
    prices = await _get_prices_for_agents(
        request,
        db,
        agent_ids=_active_agent_ids(db),
        include_benchmark=True,
    )
    leaderboard = build_leaderboard_payload(db, prices)
    activity = _paginate_activity(db, limit=settings.activity_page_size).items
    snapshots = build_snapshot_series(db, range)
    snapshots = await _ensure_benchmark_snapshots(
        request,
        db,
        range_key=range,
        snapshots=snapshots,
        leaderboard=leaderboard,
    )
    return DashboardBootstrap(
        leaderboard=leaderboard, activity=activity, snapshots=snapshots, range=range
    )


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket) -> None:
    manager = websocket.app.state.connection_manager
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
