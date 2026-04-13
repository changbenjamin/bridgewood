from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_agent, require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import (
    ActivityEventType,
    ActivityLog,
    Agent,
    BenchmarkState,
    Position,
    Trade,
    TradeSide,
    TradeStatus,
    User,
)
from app.schemas.api import (
    ActivityItem,
    ActivityPayload,
    AgentCreateRequest,
    AgentCreateResponse,
    AgentIdentity,
    DashboardBootstrap,
    LeaderboardPayload,
    MockAgentCreateRequest,
    MockAgentCreateResponse,
    PortfolioView,
    PricesResponse,
    SnapshotRange,
    TradeExecutionRequest,
    TradeExecutionResponse,
    TradeIntent,
    TradeResult,
    TradeSubmissionRequest,
    TradeSubmissionResponse,
    UserCreateRequest,
    UserCreateResponse,
)
from app.services.alpaca_client import (
    AlpacaCredentials,
    BrokerError,
    get_broker_gateway,
    get_live_benchmark_price,
)
from app.services.leaderboard import build_leaderboard_payload, build_snapshot_series
from app.services.portfolio_engine import (
    apply_fill_to_position,
    build_portfolio,
    compute_cash,
    estimate_sell_quantity,
)
from app.services.security import (
    decrypt_secret,
    encrypt_secret,
    generate_agent_api_key,
    hash_api_key,
)
from app.workers.snapshot_worker import is_market_hours


router = APIRouter()
settings = get_settings()
gateway = get_broker_gateway()


def _money(value: float | Decimal | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _get_user_credentials(user: User) -> AlpacaCredentials:
    return AlpacaCredentials(
        api_key=decrypt_secret(user.alpaca_api_key),
        secret_key=decrypt_secret(user.alpaca_secret_key),
        base_url=user.alpaca_base_url,
    )


def _slugify_username(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "agent"


def _next_mock_username(db: Session, requested_username: str | None, name: str) -> str:
    username = requested_username.strip() if requested_username else ""
    if username:
        if db.scalar(select(User).where(User.username == username)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists.",
            )
        return username

    base = _slugify_username(name)
    candidate = base
    suffix = 1
    while db.scalar(select(User).where(User.username == candidate)):
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _create_agent_record(
    *,
    db: Session,
    user: User,
    name: str,
    starting_cash: float,
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
        is_paper="paper" in user.alpaca_base_url,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent, api_key


def _build_agent_identity(agent: Agent) -> AgentIdentity:
    return AgentIdentity(
        agent_id=agent.id,
        user_id=agent.user_id,
        name=agent.name,
        icon_url=agent.icon_url,
        starting_cash=float(agent.starting_cash),
        is_paper=agent.is_paper,
    )


def _build_trade_result(trade: Trade) -> TradeResult:
    return TradeResult(
        client_order_id=trade.client_order_id,
        status=trade.status.value,
        symbol=trade.symbol,
        side=trade.side.value,
        quantity=_money(trade.quantity),
        price_per_share=_money(trade.price_per_share),
        total=_money(trade.filled_total),
        rejection_reason=trade.rejection_reason,
    )


def _generate_client_order_id(symbol: str, side: str) -> str:
    return f"{side}-{symbol.lower()}-{uuid4().hex[:12]}"


async def _ensure_benchmark_initialized(request: Request, db: Session) -> None:
    state = db.get(BenchmarkState, 1)
    if state is not None:
        return

    price_feed = request.app.state.price_feed_service
    symbol = settings.benchmark_symbol
    prices = price_feed.snapshot()
    if symbol not in prices:
        any_user = db.scalar(select(User).order_by(User.created_at.asc()))
        credentials = _get_user_credentials(any_user) if any_user is not None else None
        live_price = await get_live_benchmark_price(symbol, credentials)
        if live_price is not None:
            price_feed.prices[symbol] = live_price
            price_feed.last_updated_at = datetime.utcnow()
        prices = price_feed.snapshot()
    if symbol not in prices:
        return

    db.add(
        BenchmarkState(
            id=1,
            symbol=symbol,
            starting_cash=Decimal(str(settings.benchmark_starting_cash)),
            starting_price=prices[symbol],
        )
    )
    db.commit()


async def _process_trade_submission(
    payload: TradeSubmissionRequest,
    request: Request,
    agent: Agent,
    db: Session,
) -> tuple[TradeSubmissionResponse, int]:
    user = db.get(User, agent.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owning user not found."
        )

    duplicate_results: list[TradeResult] = []
    result_by_client_id: dict[str, TradeResult] = {}
    normalized_intents: list[tuple[TradeIntent, str]] = []
    new_intents: list[tuple[TradeIntent, str]] = []
    seen_client_ids: set[str] = set()
    for trade in payload.trades:
        client_order_id = trade.client_order_id or _generate_client_order_id(
            trade.symbol, trade.side
        )
        if client_order_id in seen_client_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Duplicate client_order_id in request.",
            )
        seen_client_ids.add(client_order_id)
        normalized_intents.append((trade, client_order_id))

        existing = db.scalar(
            select(Trade).where(Trade.client_order_id == client_order_id)
        )
        if existing:
            result = _build_trade_result(existing)
            duplicate_results.append(result)
            result_by_client_id[existing.client_order_id] = result
        else:
            new_intents.append((trade, client_order_id))

    if not new_intents and duplicate_results:
        prices = request.app.state.price_feed_service.snapshot()
        if not prices:
            await request.app.state.price_feed_service.refresh_once()
            prices = request.app.state.price_feed_service.snapshot()
        portfolio = build_portfolio(db, agent, prices)
        response = TradeSubmissionResponse(
            results=duplicate_results, portfolio_after=portfolio
        )
        return response, status.HTTP_409_CONFLICT

    credentials = _get_user_credentials(user)
    price_feed = request.app.state.price_feed_service
    latest_prices = price_feed.snapshot()

    for intent, client_order_id in new_intents:
        symbol = intent.symbol.upper()
        requested_amount = (
            Decimal(str(intent.amount_dollars))
            if intent.amount_dollars is not None
            else None
        )
        if symbol not in latest_prices:
            fetched = await gateway.get_latest_prices(credentials, [symbol])
            latest_prices.update(fetched)
            price_feed.prices.update(fetched)
        price = latest_prices.get(symbol)
        if price is None or price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to price {symbol}.",
            )

        amount = requested_amount or Decimal("0")
        try:
            if intent.side == "buy":
                if requested_amount is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"amount_dollars is required for buy trades in {symbol}.",
                    )
                amount = requested_amount
                if (
                    not settings.mock_broker_mode
                    and "/" not in symbol
                    and not is_market_hours()
                ):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Equity market orders are only accepted during regular market hours.",
                    )
                current_cash = Decimal(str(compute_cash(db, agent)))
                if amount > current_cash:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insufficient virtual cash for {symbol}.",
                    )
                account_state = await gateway.get_account_state(credentials)
                if amount > account_state.buying_power:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Actual Alpaca buying power is insufficient for {symbol}.",
                    )
                fill = await gateway.submit_order(
                    credentials,
                    symbol=symbol,
                    side="buy",
                    client_order_id=client_order_id,
                    notional=amount,
                )
            else:
                if (
                    not settings.mock_broker_mode
                    and "/" not in symbol
                    and not is_market_hours()
                ):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Equity market orders are only accepted during regular market hours.",
                    )
                position = db.get(Position, {"agent_id": agent.id, "symbol": symbol})
                if position is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"No virtual position in {symbol}.",
                    )
                if intent.sell_all:
                    qty = Decimal(position.quantity)
                    amount = (qty * price).quantize(Decimal("0.000001"))
                else:
                    if requested_amount is None:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"amount_dollars is required for sell trades in {symbol}.",
                        )
                    amount = requested_amount
                    qty = estimate_sell_quantity(position, amount, price)
                if qty <= 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Sell quantity is too small for {symbol}.",
                    )
                fill = await gateway.submit_order(
                    credentials,
                    symbol=symbol,
                    side="sell",
                    client_order_id=client_order_id,
                    qty=qty,
                )
        except HTTPException:
            raise
        except BrokerError as exc:
            rejected_trade = Trade(
                agent_id=agent.id,
                symbol=symbol,
                side=TradeSide(intent.side),
                amount_dollars=amount,
                client_order_id=client_order_id,
                rationale=payload.rationale,
                status=TradeStatus.REJECTED,
                rejection_reason=str(exc),
            )
            db.add(rejected_trade)
            db.commit()
            result_by_client_id[client_order_id] = TradeResult(
                client_order_id=client_order_id,
                status="rejected",
                symbol=symbol,
                side=intent.side,
                rejection_reason=str(exc),
            )
            continue

        status_value = (
            TradeStatus.FILLED if fill.status == "filled" else TradeStatus.REJECTED
        )
        realized_pnl = Decimal("0")
        if (
            fill.status == "filled"
            and fill.quantity is not None
            and fill.filled_avg_price is not None
        ):
            realized_pnl = apply_fill_to_position(
                db,
                agent_id=agent.id,
                symbol=symbol,
                side=TradeSide(intent.side),
                quantity=fill.quantity,
                price=fill.filled_avg_price,
            )

        trade = Trade(
            agent_id=agent.id,
            symbol=symbol,
            side=TradeSide(intent.side),
            amount_dollars=amount,
            quantity=fill.quantity,
            price_per_share=fill.filled_avg_price,
            filled_total=fill.filled_total,
            realized_pnl=realized_pnl,
            alpaca_order_id=fill.order_id,
            client_order_id=client_order_id,
            rationale=payload.rationale,
            status=status_value,
            rejection_reason=fill.rejection_reason,
            executed_at=fill.filled_at,
        )
        db.add(trade)
        db.commit()
        result_by_client_id[trade.client_order_id] = _build_trade_result(trade)

    results = [
        result_by_client_id[client_order_id]
        for _, client_order_id in normalized_intents
    ]
    metadata = {
        "trade_count": len(results),
        "results": [result.model_dump(mode="json") for result in results],
    }
    summary = payload.rationale or f"Executed {len(results)} trade(s)."
    activity = ActivityLog(
        agent_id=agent.id,
        event_type=ActivityEventType.CYCLE_SUMMARY,
        summary=summary,
        metadata_json=metadata,
        cost_tokens=(
            Decimal(str(payload.cycle_cost)) if payload.cycle_cost is not None else None
        ),
    )
    db.add(activity)
    db.commit()

    await _ensure_benchmark_initialized(request, db)
    await request.app.state.price_feed_service.refresh_once()
    prices = request.app.state.price_feed_service.snapshot()
    portfolio = build_portfolio(db, agent, prices)

    activity_payload = ActivityPayload(
        agent_id=agent.id,
        agent_name=f"{agent.name}{' *' if agent.is_paper else ''}",
        icon_url=agent.icon_url,
        summary=summary,
        cost_tokens=payload.cycle_cost,
        timestamp=activity.created_at,
    )
    await request.app.state.connection_manager.broadcast_json(
        activity_payload.model_dump(mode="json")
    )

    return (
        TradeSubmissionResponse(results=results, portfolio_after=portfolio),
        status.HTTP_200_OK,
    )


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/users", response_model=UserCreateResponse, dependencies=[Depends(require_admin)]
)
async def create_user(
    payload: UserCreateRequest, request: Request, db: Session = Depends(get_db)
) -> UserCreateResponse:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already exists."
        )

    user = User(
        username=payload.username,
        alpaca_api_key=encrypt_secret(payload.alpaca_api_key),
        alpaca_secret_key=encrypt_secret(payload.alpaca_secret_key),
        alpaca_base_url=payload.alpaca_base_url.rstrip("/"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    await _ensure_benchmark_initialized(request, db)
    return UserCreateResponse(
        user_id=user.id, username=user.username, alpaca_base_url=user.alpaca_base_url
    )


@router.post(
    "/agents", response_model=AgentCreateResponse, dependencies=[Depends(require_admin)]
)
async def create_agent(
    payload: AgentCreateRequest, db: Session = Depends(get_db)
) -> AgentCreateResponse:
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    agent, api_key = _create_agent_record(
        db=db,
        user=user,
        name=payload.name,
        starting_cash=payload.starting_cash,
        icon_url=payload.icon_url,
    )
    return AgentCreateResponse(
        agent_id=agent.id, name=agent.name, api_key=api_key, is_paper=agent.is_paper
    )


@router.post("/dev/mock-agent", response_model=MockAgentCreateResponse)
async def create_mock_agent(
    payload: MockAgentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> MockAgentCreateResponse:
    if not settings.mock_broker_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock agent bootstrap is only available when MOCK_BROKER_MODE=true.",
        )

    username = _next_mock_username(db, payload.username, payload.name)
    user = User(
        username=username,
        alpaca_api_key=encrypt_secret(f"mock-{username}-key"),
        alpaca_secret_key=encrypt_secret(f"mock-{username}-secret"),
        alpaca_base_url="https://paper-api.alpaca.markets",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    agent, api_key = _create_agent_record(
        db=db,
        user=user,
        name=payload.name,
        starting_cash=payload.starting_cash,
        icon_url=payload.icon_url,
    )

    await _ensure_benchmark_initialized(request, db)
    return MockAgentCreateResponse(
        user_id=user.id,
        agent_id=agent.id,
        name=agent.name,
        api_key=api_key,
        is_paper=agent.is_paper,
        username=user.username,
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
    db: Session = Depends(get_db),
) -> PricesResponse:
    symbol_list = [
        symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()
    ]
    price_feed = request.app.state.price_feed_service
    cached = price_feed.snapshot()
    missing = [symbol for symbol in symbol_list if symbol not in cached]
    if missing:
        user = db.get(User, agent.user_id)
        latest = await gateway.get_latest_prices(_get_user_credentials(user), missing)
        cached.update(latest)
        price_feed.prices.update(latest)
        price_feed.last_updated_at = datetime.utcnow()
    return PricesResponse(
        prices={
            symbol: float(cached[symbol]) for symbol in symbol_list if symbol in cached
        },
        as_of=price_feed.last_updated_at,
    )


@router.post("/trade", response_model=TradeExecutionResponse)
async def submit_trade(
    payload: TradeExecutionRequest,
    request: Request,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
) -> TradeExecutionResponse:
    batch_payload = TradeSubmissionRequest(
        trades=[
            TradeIntent(
                symbol=payload.symbol,
                side=payload.side,
                amount_dollars=payload.amount_dollars,
                client_order_id=payload.client_order_id,
                sell_all=payload.sell_all,
            )
        ],
        rationale=payload.rationale,
        cycle_cost=payload.cycle_cost,
    )
    response, status_code = await _process_trade_submission(
        batch_payload, request, agent, db
    )
    single_response = TradeExecutionResponse(
        result=response.results[0], portfolio_after=response.portfolio_after
    )
    if status_code != status.HTTP_200_OK:
        return JSONResponse(
            status_code=status_code,
            content=single_response.model_dump(mode="json"),
        )
    return single_response


@router.post("/trades", response_model=TradeSubmissionResponse)
async def submit_trades(
    payload: TradeSubmissionRequest,
    request: Request,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
) -> TradeSubmissionResponse:
    response, status_code = await _process_trade_submission(payload, request, agent, db)
    if status_code != status.HTTP_200_OK:
        return JSONResponse(
            status_code=status_code,
            content=response.model_dump(mode="json"),
        )
    return response


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
    logs = list(
        db.execute(
            select(ActivityLog, Agent)
            .join(Agent, Agent.id == ActivityLog.agent_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(settings.activity_page_size)
        ).all()
    )
    return [
        ActivityItem(
            id=log.id,
            agent_id=log.agent_id,
            agent_name=f"{agent.name}{' *' if agent.is_paper else ''}",
            icon_url=agent.icon_url,
            event_type=log.event_type.value,
            summary=log.summary,
            metadata=log.metadata_json,
            cost_tokens=float(log.cost_tokens) if log.cost_tokens is not None else None,
            created_at=log.created_at,
        )
        for log, agent in logs
    ]


@router.get("/snapshots")
async def get_snapshots(
    range: SnapshotRange = Query(default="1D"), db: Session = Depends(get_db)
):
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
