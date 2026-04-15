from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from typing import Any, cast

import httpx

from app.core.config import get_settings
from app.core.time import normalize_utc


settings = get_settings()
PRICE_QUANT = Decimal("0.000001")
STOOQ_URL = "https://stooq.com/q/l/"
YAHOO_CHART_URL_TEMPLATE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def is_crypto_symbol(symbol: str) -> bool:
    return "/" in symbol


class MarketDataError(Exception):
    pass


@dataclass
class MarketDataResult:
    prices: dict[str, Decimal]
    provider: str | None


@dataclass
class EquityBar:
    timestamp: datetime
    close: Decimal


class MarketDataClient:
    def _has_alpaca_credentials(self) -> bool:
        return bool(settings.alpaca_api_key and settings.alpaca_secret_key)

    def _headers(self) -> dict[str, str]:
        if not self._has_alpaca_credentials():
            raise MarketDataError("Alpaca market data credentials are not configured.")
        api_key = settings.alpaca_api_key
        secret_key = settings.alpaca_secret_key
        if api_key is None or secret_key is None:
            raise MarketDataError("Alpaca market data credentials are not configured.")
        return {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type": "application/json",
        }

    async def _get_alpaca_equity_prices(
        self, client: httpx.AsyncClient, equities: list[str]
    ) -> dict[str, Decimal]:
        if not equities:
            return {}

        response = await client.get(
            f"{settings.alpaca_data_url}/v2/stocks/trades/latest",
            headers=self._headers(),
            params={
                "symbols": ",".join(equities),
                "feed": settings.alpaca_equity_feed,
            },
        )
        if response.status_code >= 400:
            raise MarketDataError(response.text)
        payload = response.json().get("trades", {})
        return {
            symbol: to_decimal(data["p"])
            for symbol, data in payload.items()
            if data.get("p") is not None
        }

    async def _get_alpaca_equity_bars(
        self,
        client: httpx.AsyncClient,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[EquityBar]:
        response = await client.get(
            f"{settings.alpaca_data_url}/v2/stocks/bars",
            headers=self._headers(),
            params={
                "symbols": symbol,
                "timeframe": timeframe,
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
                "feed": settings.alpaca_equity_feed,
                "adjustment": "raw",
                "sort": "asc",
                "limit": 10000,
            },
        )
        if response.status_code >= 400:
            raise MarketDataError(response.text)

        payload = response.json().get("bars", {})
        rows = payload.get(symbol, [])
        bars: list[EquityBar] = []
        for row in rows:
            close = row.get("c")
            timestamp = row.get("t")
            if close is None or timestamp is None:
                continue
            parsed_timestamp = normalize_utc(
                datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            )
            bars.append(EquityBar(timestamp=parsed_timestamp, close=to_decimal(close)))
        return bars

    async def _get_alpaca_crypto_prices(
        self, client: httpx.AsyncClient, crypto: list[str]
    ) -> dict[str, Decimal]:
        if not crypto:
            return {}

        response = await client.get(
            f"{settings.alpaca_data_url}/v1beta3/crypto/us/latest/trades",
            headers=self._headers(),
            params={"symbols": ",".join(crypto)},
        )
        if response.status_code >= 400:
            raise MarketDataError(response.text)
        payload = response.json().get("trades", {})
        return {
            symbol: to_decimal(data["p"])
            for symbol, data in payload.items()
            if data.get("p") is not None
        }

    async def _get_stooq_equity_price(
        self, client: httpx.AsyncClient, symbol: str
    ) -> tuple[str, Decimal] | None:
        response = await client.get(
            STOOQ_URL,
            params={
                "s": f"{symbol.lower()}.us",
                "f": "sd2t2ohlcvn",
                "e": "csv",
            },
        )
        if response.status_code >= 400:
            raise MarketDataError(response.text)

        rows = list(csv.reader(StringIO(response.text.strip())))
        if not rows:
            return None

        first_row = rows[0]
        if len(first_row) < 7 or first_row[1] == "N/D" or first_row[6] == "N/D":
            return None

        return symbol, to_decimal(first_row[6])

    async def _get_yahoo_equity_price(
        self, client: httpx.AsyncClient, symbol: str
    ) -> tuple[str, Decimal] | None:
        response = await client.get(
            YAHOO_CHART_URL_TEMPLATE.format(symbol=symbol),
            params={
                "interval": "1m",
                "range": "1d",
                "includePrePost": "false",
            },
            headers=YAHOO_HEADERS,
        )
        if response.status_code >= 400:
            raise MarketDataError(response.text)

        payload = response.json().get("chart", {})
        results = payload.get("result") or []
        if not results:
            return None

        result = results[0]
        meta = result.get("meta", {})
        regular_market_price = meta.get("regularMarketPrice")
        if regular_market_price is not None:
            return symbol, to_decimal(regular_market_price)

        quotes = result.get("indicators", {}).get("quote", [])
        if not quotes:
            return None

        closes = quotes[0].get("close", [])
        for close in reversed(closes):
            if close is not None:
                return symbol, to_decimal(close)
        return None

    async def _get_yahoo_equity_prices(
        self, client: httpx.AsyncClient, equities: list[str]
    ) -> dict[str, Decimal]:
        if not equities:
            return {}

        raw_results = await asyncio.gather(
            *(self._get_yahoo_equity_price(client, symbol) for symbol in equities),
            return_exceptions=True,
        )
        results = cast(list[tuple[str, Decimal] | Exception | None], raw_results)
        prices: dict[str, Decimal] = {}
        errors: list[Exception] = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(result)
                continue
            if result is None:
                continue
            symbol, price = result
            prices[symbol] = price

        if prices:
            return prices
        if errors:
            raise MarketDataError(str(errors[0]))
        return {}

    async def _get_stooq_equity_prices(
        self, client: httpx.AsyncClient, equities: list[str]
    ) -> dict[str, Decimal]:
        if not equities:
            return {}

        raw_results = await asyncio.gather(
            *(self._get_stooq_equity_price(client, symbol) for symbol in equities),
            return_exceptions=True,
        )
        results = cast(list[tuple[str, Decimal] | Exception | None], raw_results)
        prices: dict[str, Decimal] = {}
        errors: list[Exception] = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(result)
                continue
            if result is None:
                continue
            symbol, price = result
            prices[symbol] = price

        if prices:
            return prices
        if errors:
            raise MarketDataError(str(errors[0]))
        return {}

    async def _get_public_equity_fallback_prices(
        self, client: httpx.AsyncClient, equities: list[str]
    ) -> tuple[dict[str, Decimal], str | None]:
        if not equities:
            return {}, None

        prices: dict[str, Decimal] = {}
        provider: str | None = None

        try:
            yahoo_prices = await self._get_yahoo_equity_prices(client, equities)
            if yahoo_prices:
                prices.update(yahoo_prices)
                provider = "yahoo"
        except MarketDataError:
            yahoo_prices = {}

        missing_equities = [symbol for symbol in equities if symbol not in prices]
        if missing_equities:
            try:
                stooq_prices = await self._get_stooq_equity_prices(
                    client, missing_equities
                )
                if stooq_prices:
                    prices.update(stooq_prices)
                    if provider is None:
                        provider = "stooq"
            except MarketDataError:
                stooq_prices = {}

        return prices, provider

    async def get_latest_prices(self, symbols: list[str]) -> MarketDataResult:
        normalized_symbols = sorted({normalize_symbol(symbol) for symbol in symbols})
        if not normalized_symbols:
            return MarketDataResult(prices={}, provider=None)

        equities = [
            symbol for symbol in normalized_symbols if not is_crypto_symbol(symbol)
        ]
        crypto = [symbol for symbol in normalized_symbols if is_crypto_symbol(symbol)]
        prices: dict[str, Decimal] = {}
        provider: str | None = None

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            if equities and self._has_alpaca_credentials():
                try:
                    alpaca_equities = await self._get_alpaca_equity_prices(
                        client, equities
                    )
                    if alpaca_equities:
                        prices.update(alpaca_equities)
                        provider = "alpaca"
                except MarketDataError:
                    fallback_equities, fallback_provider = (
                        await self._get_public_equity_fallback_prices(client, equities)
                    )
                    if fallback_equities:
                        prices.update(fallback_equities)
                        provider = fallback_provider
            elif equities:
                fallback_equities, fallback_provider = (
                    await self._get_public_equity_fallback_prices(client, equities)
                )
                if fallback_equities:
                    prices.update(fallback_equities)
                    provider = fallback_provider

            missing_equities = [symbol for symbol in equities if symbol not in prices]
            if missing_equities:
                fallback_equities, fallback_provider = (
                    await self._get_public_equity_fallback_prices(
                        client, missing_equities
                    )
                )
                if fallback_equities:
                    prices.update(fallback_equities)
                    if provider is None:
                        provider = fallback_provider

            if crypto:
                crypto_prices = await self._get_alpaca_crypto_prices(client, crypto)
                if crypto_prices:
                    prices.update(crypto_prices)
                    if provider is None:
                        provider = "alpaca"

        return MarketDataResult(prices=prices, provider=provider)

    async def get_equity_bars(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> list[EquityBar]:
        normalized_symbol = normalize_symbol(symbol)
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            return await self._get_alpaca_equity_bars(
                client,
                normalized_symbol,
                start=normalize_utc(start),
                end=normalize_utc(end),
                timeframe=timeframe,
            )
