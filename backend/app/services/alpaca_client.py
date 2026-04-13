from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings


settings = get_settings()
PRICE_QUANT = Decimal("0.000001")
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def is_crypto_symbol(symbol: str) -> bool:
    return "/" in symbol


def is_regular_equity_market_hours(now: datetime | None = None) -> bool:
    current = (now or datetime.utcnow()).astimezone(ZoneInfo("America/New_York"))
    if current.weekday() >= 5:
        return False
    opening = current.replace(hour=9, minute=30, second=0, microsecond=0)
    closing = current.replace(hour=16, minute=0, second=0, microsecond=0)
    return opening <= current <= closing


@dataclass
class AlpacaCredentials:
    api_key: str
    secret_key: str
    base_url: str


@dataclass
class AccountState:
    buying_power: Decimal
    cash: Decimal | None = None


@dataclass
class OrderFill:
    order_id: str
    client_order_id: str
    status: str
    symbol: str
    side: str
    quantity: Decimal | None
    filled_avg_price: Decimal | None
    filled_total: Decimal | None
    rejection_reason: str | None = None
    filled_at: datetime | None = None


class BrokerError(Exception):
    pass


class MarketClosedError(BrokerError):
    pass


class BaseBrokerGateway:
    async def get_account_state(self, credentials: AlpacaCredentials) -> AccountState:
        raise NotImplementedError

    async def get_latest_prices(
        self, credentials: AlpacaCredentials | None, symbols: list[str]
    ) -> dict[str, Decimal]:
        raise NotImplementedError

    async def submit_order(
        self,
        credentials: AlpacaCredentials,
        *,
        symbol: str,
        side: str,
        client_order_id: str,
        notional: Decimal | None = None,
        qty: Decimal | None = None,
    ) -> OrderFill:
        raise NotImplementedError

    async def advance_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        return {}


class MockBrokerGateway(BaseBrokerGateway):
    def __init__(self) -> None:
        self.random = random.Random(7)
        self.prices: dict[str, Decimal] = {
            "AAPL": Decimal("187.52"),
            "TSLA": Decimal("171.84"),
            "NVDA": Decimal("906.11"),
            "MSFT": Decimal("421.23"),
            "META": Decimal("514.90"),
            "SPY": Decimal("533.10"),
            "BTC/USD": Decimal("68750.00"),
            "ETH/USD": Decimal("3410.00"),
        }

    def _ensure_price(self, symbol: str) -> Decimal:
        symbol = normalize_symbol(symbol)
        if symbol not in self.prices:
            base = (sum(ord(char) for char in symbol) % 250) + 20
            self.prices[symbol] = Decimal(str(base)).quantize(PRICE_QUANT)
        return self.prices[symbol]

    async def get_account_state(self, credentials: AlpacaCredentials) -> AccountState:
        return AccountState(
            buying_power=Decimal("1000000.00"), cash=Decimal("1000000.00")
        )

    async def get_latest_prices(
        self, credentials: AlpacaCredentials | None, symbols: list[str]
    ) -> dict[str, Decimal]:
        return {
            normalize_symbol(symbol): self._ensure_price(symbol) for symbol in symbols
        }

    async def submit_order(
        self,
        credentials: AlpacaCredentials,
        *,
        symbol: str,
        side: str,
        client_order_id: str,
        notional: Decimal | None = None,
        qty: Decimal | None = None,
    ) -> OrderFill:
        price = self._ensure_price(symbol)
        if notional is None and qty is None:
            raise BrokerError("Either notional or qty must be provided.")
        if qty is None:
            assert notional is not None
            qty = (notional / price).quantize(Decimal("0.000001"))
        filled_total = (qty * price).quantize(PRICE_QUANT)
        await asyncio.sleep(0)
        return OrderFill(
            order_id=f"mock-{client_order_id}",
            client_order_id=client_order_id,
            status="filled",
            symbol=normalize_symbol(symbol),
            side=side,
            quantity=qty,
            filled_avg_price=price,
            filled_total=filled_total,
            filled_at=datetime.utcnow(),
        )

    async def advance_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        updated: dict[str, Decimal] = {}
        for symbol in symbols:
            current = self._ensure_price(symbol)
            drift = Decimal(str(self.random.uniform(-0.0075, 0.0075)))
            bumped = (current * (Decimal("1") + drift)).quantize(PRICE_QUANT)
            self.prices[normalize_symbol(symbol)] = max(bumped, Decimal("1.00"))
            updated[normalize_symbol(symbol)] = self.prices[normalize_symbol(symbol)]
        return updated


class RealBrokerGateway(BaseBrokerGateway):
    def _headers(self, credentials: AlpacaCredentials) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": credentials.api_key,
            "APCA-API-SECRET-KEY": credentials.secret_key,
            "Content-Type": "application/json",
        }

    def _data_url(self, credentials: AlpacaCredentials) -> str:
        if "sandbox" in credentials.base_url:
            return settings.alpaca_sandbox_data_url
        return settings.alpaca_data_url

    async def get_account_state(self, credentials: AlpacaCredentials) -> AccountState:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{credentials.base_url}/v2/account", headers=self._headers(credentials)
            )
            response.raise_for_status()
        payload = response.json()
        return AccountState(
            buying_power=to_decimal(payload["buying_power"]),
            cash=(
                to_decimal(payload.get("cash"))
                if payload.get("cash") is not None
                else None
            ),
        )

    async def get_latest_prices(
        self, credentials: AlpacaCredentials | None, symbols: list[str]
    ) -> dict[str, Decimal]:
        if credentials is None:
            raise BrokerError(
                "Market data requires at least one user credential in live mode."
            )

        equities = sorted(
            {
                normalize_symbol(symbol)
                for symbol in symbols
                if not is_crypto_symbol(symbol)
            }
        )
        crypto = sorted(
            {normalize_symbol(symbol) for symbol in symbols if is_crypto_symbol(symbol)}
        )
        prices: dict[str, Decimal] = {}

        async with httpx.AsyncClient(timeout=15) as client:
            if equities:
                response = await client.get(
                    f"{self._data_url(credentials)}/v2/stocks/trades/latest",
                    headers=self._headers(credentials),
                    params={
                        "symbols": ",".join(equities),
                        "feed": settings.alpaca_equity_feed,
                    },
                )
                response.raise_for_status()
                payload = response.json().get("trades", {})
                prices.update(
                    {symbol: to_decimal(data["p"]) for symbol, data in payload.items()}
                )

            if crypto:
                response = await client.get(
                    f"{self._data_url(credentials)}/v1beta3/crypto/us/latest/trades",
                    headers=self._headers(credentials),
                    params={"symbols": ",".join(crypto)},
                )
                response.raise_for_status()
                payload = response.json().get("trades", {})
                prices.update(
                    {symbol: to_decimal(data["p"]) for symbol, data in payload.items()}
                )

        return prices

    async def submit_order(
        self,
        credentials: AlpacaCredentials,
        *,
        symbol: str,
        side: str,
        client_order_id: str,
        notional: Decimal | None = None,
        qty: Decimal | None = None,
    ) -> OrderFill:
        payload: dict[str, Any] = {
            "symbol": normalize_symbol(symbol),
            "side": side,
            "type": "market",
            "client_order_id": client_order_id,
        }

        if is_crypto_symbol(symbol):
            payload["time_in_force"] = "gtc"
        else:
            payload["time_in_force"] = "day"

        if notional is not None:
            payload["notional"] = str(notional)
        if qty is not None:
            payload["qty"] = str(qty)

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{credentials.base_url}/v2/orders",
                headers=self._headers(credentials),
                json=payload,
            )
            if response.status_code >= 400:
                detail = response.text
                raise BrokerError(detail)
            response.raise_for_status()

        return await self.wait_for_fill(credentials, client_order_id)

    async def wait_for_fill(
        self, credentials: AlpacaCredentials, client_order_id: str
    ) -> OrderFill:
        attempts = max(
            int(settings.order_fill_timeout_seconds / settings.order_fill_poll_seconds),
            1,
        )
        async with httpx.AsyncClient(timeout=15) as client:
            for _ in range(attempts):
                response = await client.get(
                    f"{credentials.base_url}/v2/orders:by_client_order_id",
                    headers=self._headers(credentials),
                    params={"client_order_id": client_order_id},
                )
                response.raise_for_status()
                payload = response.json()
                status = payload["status"]
                if status in {"filled", "rejected", "canceled", "expired"}:
                    qty = (
                        to_decimal(payload["filled_qty"])
                        if payload.get("filled_qty")
                        else None
                    )
                    price = (
                        to_decimal(payload["filled_avg_price"])
                        if payload.get("filled_avg_price")
                        else None
                    )
                    filled_total = (
                        (qty * price).quantize(PRICE_QUANT) if qty and price else None
                    )
                    return OrderFill(
                        order_id=payload["id"],
                        client_order_id=payload["client_order_id"],
                        status="filled" if status == "filled" else "rejected",
                        symbol=payload["symbol"],
                        side=payload["side"],
                        quantity=qty,
                        filled_avg_price=price,
                        filled_total=filled_total,
                        rejection_reason=payload.get("reject_reason")
                        or payload.get("status"),
                        filled_at=(
                            datetime.fromisoformat(
                                payload["filled_at"].replace("Z", "+00:00")
                            )
                            if payload.get("filled_at")
                            else datetime.utcnow()
                        ),
                    )
                await asyncio.sleep(settings.order_fill_poll_seconds)
        raise BrokerError(f"Timed out waiting for fill for {client_order_id}.")


_broker_gateway: BaseBrokerGateway | None = None


def get_broker_gateway() -> BaseBrokerGateway:
    global _broker_gateway
    if _broker_gateway is None:
        _broker_gateway = (
            MockBrokerGateway() if settings.mock_broker_mode else RealBrokerGateway()
        )
    return _broker_gateway


async def get_live_benchmark_price(
    symbol: str, credentials: AlpacaCredentials | None
) -> Decimal | None:
    normalized_symbol = normalize_symbol(symbol)
    use_intraday = is_regular_equity_market_hours()

    if credentials is not None and use_intraday:
        try:
            live_prices = await RealBrokerGateway().get_latest_prices(
                credentials, [normalized_symbol]
            )
            price = live_prices.get(normalized_symbol)
            if price is not None:
                return price
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{YAHOO_CHART_URL}/{normalized_symbol}",
                params=(
                    {"interval": "1m", "range": "1d"}
                    if use_intraday
                    else {"interval": "1d", "range": "5d"}
                ),
            )
            response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    results = payload.get("chart", {}).get("result") or []
    if not results:
        return None

    result = results[0]
    meta = result.get("meta", {})
    if use_intraday and meta.get("regularMarketPrice") is not None:
        return to_decimal(meta["regularMarketPrice"])

    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    for close in reversed(closes):
        if close is not None:
            return to_decimal(close)

    return None
