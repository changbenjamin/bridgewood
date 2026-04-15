from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import BridgewoodError
from app.core.time import utc_now
from app.models.entities import (
    Agent,
    CashAdjustment,
    CashAdjustmentKind,
    Execution,
    ExecutionSide,
    PortfolioSnapshot,
    Position,
)
from app.schemas.api import PortfolioView, PositionView


MONEY = Decimal("0.01")
NOTIONAL = Decimal("0.000001")
PRICE = Decimal("0.000001")
QUANTITY = Decimal("0.000000001")
RETURN_PCT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def notional(value: Decimal) -> Decimal:
    return value.quantize(NOTIONAL, rounding=ROUND_HALF_UP)


def price_value(value: Decimal) -> Decimal:
    return value.quantize(PRICE, rounding=ROUND_HALF_UP)


def quantity_value(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY, rounding=ROUND_HALF_UP)


def scalar_decimal(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")


def return_pct_value(value: Decimal) -> Decimal:
    return value.quantize(RETURN_PCT, rounding=ROUND_HALF_UP)


def gross_notional(quantity: Decimal, price: Decimal) -> Decimal:
    return notional(quantity * price)


def signed_cash_adjustment_amount(kind: CashAdjustmentKind, amount: Decimal) -> Decimal:
    if kind == CashAdjustmentKind.DEPOSIT:
        return amount
    return -amount


def cash_adjustment_total(
    db: Session,
    agent_id: str,
    *,
    start_after: datetime | None = None,
    end_at: datetime | None = None,
) -> Decimal:
    signed_amount = case(
        (CashAdjustment.kind == CashAdjustmentKind.DEPOSIT, CashAdjustment.amount),
        else_=-CashAdjustment.amount,
    )
    query = select(func.sum(signed_amount)).where(CashAdjustment.agent_id == agent_id)
    if start_after is not None:
        query = query.where(CashAdjustment.effective_at > start_after)
    if end_at is not None:
        query = query.where(CashAdjustment.effective_at <= end_at)
    return scalar_decimal(db.scalar(query))


def contributed_capital(
    db: Session, agent: Agent, *, as_of: datetime | None = None
) -> Decimal:
    return money(
        Decimal(agent.starting_cash) + cash_adjustment_total(db, agent.id, end_at=as_of)
    )


def time_weighted_return_series(
    agent: Agent,
    valuations: list[tuple[datetime, Decimal]],
    adjustments: list[CashAdjustment],
) -> list[tuple[datetime, Decimal]]:
    previous_at = agent.created_at
    previous_value = money(Decimal(agent.starting_cash))
    cumulative_factor = Decimal("1")
    adjustment_index = 0
    series: list[tuple[datetime, Decimal]] = []

    for point_at, point_total_value in valuations:
        net_flow = Decimal("0")
        while (
            adjustment_index < len(adjustments)
            and adjustments[adjustment_index].effective_at <= point_at
        ):
            adjustment = adjustments[adjustment_index]
            if adjustment.effective_at > previous_at:
                net_flow += adjustment.signed_amount
            adjustment_index += 1

        if previous_value > 0:
            period_factor = (point_total_value - net_flow) / previous_value
            cumulative_factor *= max(period_factor, Decimal("0"))

        series.append(
            (
                point_at,
                return_pct_value((cumulative_factor - Decimal("1")) * Decimal("100")),
            )
        )
        previous_at = point_at
        previous_value = point_total_value

    return series


def compute_time_weighted_return_pct(
    db: Session,
    agent: Agent,
    *,
    total_value: Decimal,
    as_of: datetime | None = None,
) -> Decimal:
    point_at = as_of or utc_now()
    snapshots = list(
        db.scalars(
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.agent_id == agent.id,
                PortfolioSnapshot.snapshot_at <= point_at,
            )
            .order_by(PortfolioSnapshot.snapshot_at.asc(), PortfolioSnapshot.id.asc())
        ).all()
    )
    valuations = [
        (snapshot.snapshot_at, money(Decimal(snapshot.total_value)))
        for snapshot in snapshots
    ]
    if valuations and valuations[-1][0] == point_at:
        valuations[-1] = (point_at, money(total_value))
    else:
        valuations.append((point_at, money(total_value)))

    adjustments = list(
        db.scalars(
            select(CashAdjustment)
            .where(
                CashAdjustment.agent_id == agent.id,
                CashAdjustment.effective_at <= point_at,
            )
            .order_by(
                CashAdjustment.effective_at.asc(),
                CashAdjustment.created_at.asc(),
                CashAdjustment.id.asc(),
            )
        ).all()
    )
    series = time_weighted_return_series(agent, valuations, adjustments)
    if not series:
        return Decimal("0")
    return series[-1][1]


def compute_cash(
    db: Session,
    agent: Agent,
    *,
    net_cash_adjustments: Decimal | None = None,
) -> Decimal:
    net_cash_adjustments = (
        cash_adjustment_total(db, agent.id)
        if net_cash_adjustments is None
        else net_cash_adjustments
    )
    buy_total = scalar_decimal(
        db.scalar(
            select(func.sum(Execution.gross_notional)).where(
                Execution.agent_id == agent.id,
                Execution.side == ExecutionSide.BUY,
            )
        )
    )
    sell_total = scalar_decimal(
        db.scalar(
            select(func.sum(Execution.gross_notional)).where(
                Execution.agent_id == agent.id,
                Execution.side == ExecutionSide.SELL,
            )
        )
    )
    fees_total = scalar_decimal(
        db.scalar(
            select(func.sum(Execution.fees)).where(
                Execution.agent_id == agent.id,
            )
        )
    )
    return money(
        Decimal(agent.starting_cash)
        + net_cash_adjustments
        - buy_total
        + sell_total
        - fees_total
    )


def get_positions(db: Session, agent_id: str) -> list[Position]:
    return list(
        db.scalars(
            select(Position)
            .where(Position.agent_id == agent_id)
            .order_by(Position.symbol.asc())
        )
    )


def build_portfolio(
    db: Session,
    agent: Agent,
    prices: dict[str, Decimal],
    *,
    as_of: datetime | None = None,
) -> PortfolioView:
    net_cash_adjustments = cash_adjustment_total(db, agent.id, end_at=as_of)
    capital = money(Decimal(agent.starting_cash) + net_cash_adjustments)
    cash = compute_cash(db, agent, net_cash_adjustments=net_cash_adjustments)
    holdings = []
    positions = get_positions(db, agent.id)
    total_market_value = Decimal("0")

    for position in positions:
        price = prices.get(position.symbol, Decimal(position.avg_cost_basis))
        market_value = money(Decimal(position.quantity) * price)
        total_market_value += market_value
        holdings.append(
            PositionView(
                symbol=position.symbol,
                quantity=float(position.quantity),
                market_value=float(market_value),
                avg_cost=float(position.avg_cost_basis),
            )
        )

    total_value = money(cash + total_market_value)
    pnl = money(total_value - capital)
    return_pct = compute_time_weighted_return_pct(
        db,
        agent,
        total_value=total_value,
        as_of=as_of,
    )

    return PortfolioView(
        agent_id=agent.id,
        starting_cash=float(Decimal(agent.starting_cash)),
        net_cash_adjustments=float(money(net_cash_adjustments)),
        contributed_capital=float(capital),
        cash=float(cash),
        total_value=float(total_value),
        pnl=float(pnl),
        return_pct=float(return_pct),
        positions=holdings,
    )


def apply_execution_to_position(
    db: Session,
    *,
    agent_id: str,
    symbol: str,
    side: ExecutionSide,
    quantity: Decimal,
    price: Decimal,
    fees: Decimal,
) -> Decimal:
    position = db.get(Position, {"agent_id": agent_id, "symbol": symbol})
    realized_pnl = Decimal("0")

    if side == ExecutionSide.BUY:
        if position is None:
            position = Position(
                agent_id=agent_id,
                symbol=symbol,
                quantity=quantity_value(quantity),
                avg_cost_basis=price_value(price),
                updated_at=utc_now(),
            )
            db.add(position)
            return realized_pnl

        current_qty = Decimal(position.quantity)
        current_avg = Decimal(position.avg_cost_basis)
        new_quantity = quantity_value(current_qty + quantity)
        new_avg_cost = price_value(
            ((current_qty * current_avg) + (quantity * price)) / new_quantity
        )
        position.quantity = new_quantity
        position.avg_cost_basis = new_avg_cost
        position.updated_at = utc_now()
        return realized_pnl

    if position is None or Decimal(position.quantity) <= Decimal("0"):
        raise BridgewoodError(
            status_code=400,
            detail=f"No position available to sell for {symbol}.",
            code="NO_POSITION",
        )

    current_qty = Decimal(position.quantity)
    if quantity > current_qty + QUANTITY:
        raise BridgewoodError(
            status_code=400,
            detail=f"Insufficient quantity to sell {quantity} {symbol}.",
            code="INSUFFICIENT_POSITION",
        )

    realized_pnl = money(((price - Decimal(position.avg_cost_basis)) * quantity) - fees)
    remaining = quantity_value(max(current_qty - quantity, Decimal("0")))
    if remaining <= Decimal("0"):
        db.delete(position)
    else:
        position.quantity = remaining
        position.updated_at = utc_now()
    return realized_pnl
