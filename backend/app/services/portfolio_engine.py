from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BridgewoodError
from app.core.time import utc_now
from app.models.entities import Agent, Execution, ExecutionSide, Position
from app.schemas.api import PortfolioView, PositionView


MONEY = Decimal("0.01")
NOTIONAL = Decimal("0.000001")
PRICE = Decimal("0.000001")
QUANTITY = Decimal("0.000000001")


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


def gross_notional(quantity: Decimal, price: Decimal) -> Decimal:
    return notional(quantity * price)


def compute_cash(db: Session, agent: Agent) -> Decimal:
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
    return money(Decimal(agent.starting_cash) - buy_total + sell_total - fees_total)


def get_positions(db: Session, agent_id: str) -> list[Position]:
    return list(
        db.scalars(
            select(Position)
            .where(Position.agent_id == agent_id)
            .order_by(Position.symbol.asc())
        )
    )


def build_portfolio(
    db: Session, agent: Agent, prices: dict[str, Decimal]
) -> PortfolioView:
    cash = compute_cash(db, agent)
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
    pnl = money(total_value - Decimal(agent.starting_cash))
    return_pct = Decimal("0")
    if agent.starting_cash:
        return_pct = (pnl / Decimal(agent.starting_cash) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return PortfolioView(
        agent_id=agent.id,
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
