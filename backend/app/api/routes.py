from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_account_user, get_current_agent
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import (
    Agent,
    BenchmarkState,
    Execution,
    ExecutionSide,
    TradingMode,
    User,
)
from app.schemas.api import (
    AccountAgentCreateRequest,
    AccountAgentSummary,
    AccountIdentity,
    AccountOverview,
    ActivityItem,
    ActivityPayload,
    AgentCreateResponse,
    AgentIdentity,
    DashboardBootstrap,
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
from app.services.leaderboard import build_leaderboard_payload, build_snapshot_series
from app.services.portfolio_engine import (
    apply_execution_to_position,
    build_portfolio,
    gross_notional,
    notional,
    price_value,
    quantity_value,
)
from app.services.security import generate_account_api_key, generate_agent_api_key, hash_api_key


router = APIRouter()
settings = get_settings()


def _display_name(agent: Agent) -> str:
    return f"{agent.name}{' *' if agent.is_paper else ''}"


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _format_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        return text.rstrip("0").rstrip(".")
    return text


def _build_execution_summary(agent: Agent, execution: Execution) -> str:
    action = "bought" if execution.side == ExecutionSide.BUY else "sold"
    quantity = _format_decimal(Decimal(execution.quantity))
    price = Decimal(execution.price_per_share).quantize(Decimal("0.01"))
    return f"{_display_name(agent)} {action} {quantity} {execution.symbol} @ ${price}"


def _build_execution_metadata(execution: Execution) -> dict[str, str | float]:
    return {
        "external_order_id": execution.external_order_id,
        "symbol": execution.symbol,
        "side": execution.side.value,
        "quantity": float(execution.quantity),
        "price_per_share": float(execution.price_per_share),
        "gross_notional": float(execution.gross_notional),
        "fees": float(execution.fees),
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
    )


def _build_execution_result(
    execution: Execution, *, status_value: str
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


@router.get("/health")
async def healthcheck() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "market_data_configured": bool(
            settings.alpaca_api_key and settings.alpaca_secret_key
        ),
    }


@router.post(
    "/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED
)
async def signup(
    payload: SignupRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SignupResponse:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
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
    prices = request.app.state.price_feed_service.snapshot()
    if not prices:
        await request.app.state.price_feed_service.refresh_once()
        prices = request.app.state.price_feed_service.snapshot()
    return build_portfolio(db, agent, prices)


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
    seen_external_ids: set[str] = set()
    result_by_external_id: dict[str, ExecutionResult] = {}
    new_executions = []

    for execution in payload.executions:
        if execution.external_order_id in seen_external_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Duplicate external_order_id in request.",
            )
        seen_external_ids.add(execution.external_order_id)

        existing = db.scalar(
            select(Execution).where(
                Execution.agent_id == agent.id,
                Execution.external_order_id == execution.external_order_id,
            )
        )
        if existing is not None:
            result_by_external_id[execution.external_order_id] = _build_execution_result(
                existing, status_value="duplicate"
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
            result_by_external_id[execution.external_order_id] = _build_execution_result(
                execution_model, status_value="recorded"
            )

        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    await _ensure_benchmark_initialized(request, db)
    await request.app.state.price_feed_service.refresh_once()
    prices = request.app.state.price_feed_service.snapshot()
    portfolio = build_portfolio(db, agent, prices)

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
    if not request.app.state.price_feed_service.snapshot():
        await request.app.state.price_feed_service.refresh_once()
    return build_leaderboard_payload(
        db, request.app.state.price_feed_service.snapshot()
    )


@router.get("/activity", response_model=list[ActivityItem])
async def get_activity(db: Session = Depends(get_db)) -> list[ActivityItem]:
    rows = list(
        db.execute(
            select(Execution, Agent)
            .join(Agent, Agent.id == Execution.agent_id)
            .order_by(Execution.executed_at.desc(), Execution.created_at.desc())
            .limit(settings.activity_page_size)
        ).all()
    )
    return [_build_activity_item(execution, agent) for execution, agent in rows]


@router.get("/snapshots", response_model=list[SnapshotPoint])
async def get_snapshots(
    range: SnapshotRange = Query(default="1D"), db: Session = Depends(get_db)
) -> list[SnapshotPoint]:
    return build_snapshot_series(db, range)


@router.get("/dashboard", response_model=DashboardBootstrap)
async def get_dashboard(
    request: Request,
    range: SnapshotRange = Query(default="1D"),
    db: Session = Depends(get_db),
) -> DashboardBootstrap:
    await _ensure_benchmark_initialized(request, db)
    if not request.app.state.price_feed_service.snapshot():
        await request.app.state.price_feed_service.refresh_once()
    leaderboard = build_leaderboard_payload(
        db, request.app.state.price_feed_service.snapshot()
    )
    activity = await get_activity(db)
    snapshots = build_snapshot_series(db, range)
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
