from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Agent, Position, Trade, TradeSide, TradeStatus
from app.schemas.api import PortfolioView, PositionView


MONEY = Decimal("0.01")
SHARES = Decimal("0.000001")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def shares(value: Decimal) -> Decimal:
    return value.quantize(SHARES, rounding=ROUND_HALF_UP)


def scalar_decimal(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")


def compute_cash(db: Session, agent: Agent) -> Decimal:
    buy_total = scalar_decimal(
        db.scalar(
            select(func.sum(Trade.filled_total)).where(
                Trade.agent_id == agent.id,
                Trade.status == TradeStatus.FILLED,
                Trade.side == TradeSide.BUY,
            )
        )
    )
    sell_total = scalar_decimal(
        db.scalar(
            select(func.sum(Trade.filled_total)).where(
                Trade.agent_id == agent.id,
                Trade.status == TradeStatus.FILLED,
                Trade.side == TradeSide.SELL,
            )
        )
    )
    return money(Decimal(agent.starting_cash) - buy_total + sell_total)


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


def apply_fill_to_position(
    db: Session,
    *,
    agent_id: str,
    symbol: str,
    side: TradeSide,
    quantity: Decimal,
    price: Decimal,
) -> Decimal:
    position = db.get(Position, {"agent_id": agent_id, "symbol": symbol})
    realized_pnl = Decimal("0")

    if side == TradeSide.BUY:
        if position is None:
            position = Position(
                agent_id=agent_id,
                symbol=symbol,
                quantity=shares(quantity),
                avg_cost_basis=money(price),
                updated_at=datetime.utcnow(),
            )
            db.add(position)
            return realized_pnl

        current_qty = Decimal(position.quantity)
        current_avg = Decimal(position.avg_cost_basis)
        new_quantity = shares(current_qty + quantity)
        new_avg_cost = money(
            ((current_qty * current_avg) + (quantity * price)) / new_quantity
        )
        position.quantity = new_quantity
        position.avg_cost_basis = new_avg_cost
        position.updated_at = datetime.utcnow()
        return realized_pnl

    if position is None or Decimal(position.quantity) <= Decimal("0"):
        raise ValueError(f"No position available to sell for {symbol}.")

    current_qty = Decimal(position.quantity)
    if quantity > current_qty + Decimal("0.000001"):
        raise ValueError(f"Insufficient quantity to sell {quantity} {symbol}.")

    realized_pnl = money((price - Decimal(position.avg_cost_basis)) * quantity)
    remaining = shares(max(current_qty - quantity, Decimal("0")))
    if remaining <= Decimal("0.000000"):
        db.delete(position)
    else:
        position.quantity = remaining
        position.updated_at = datetime.utcnow()
    return realized_pnl


def estimate_sell_quantity(
    position: Position, amount_dollars: Decimal, price: Decimal
) -> Decimal:
    max_qty = Decimal(position.quantity)
    if amount_dollars >= max_qty * price:
        return shares(max_qty)
    return shares(amount_dollars / price)


def group_prices_by_symbol(
    agents: list[Agent], positions: list[Position]
) -> dict[str, list[str]]:
    grouped = defaultdict(list)
    for position in positions:
        grouped[position.symbol].append(position.agent_id)
    return grouped
