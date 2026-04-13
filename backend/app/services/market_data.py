from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx

from app.core.config import get_settings


settings = get_settings()
PRICE_QUANT = Decimal("0.000001")


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def is_crypto_symbol(symbol: str) -> bool:
    return "/" in symbol


class MarketDataError(Exception):
    pass


class MarketDataClient:
    def _headers(self) -> dict[str, str]:
        if not settings.alpaca_api_key or not settings.alpaca_secret_key:
            raise MarketDataError("Alpaca market data credentials are not configured.")
        return {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
            "Content-Type": "application/json",
        }

    async def get_latest_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        normalized_symbols = sorted({normalize_symbol(symbol) for symbol in symbols})
        if not normalized_symbols:
            return {}

        equities = [symbol for symbol in normalized_symbols if not is_crypto_symbol(symbol)]
        crypto = [symbol for symbol in normalized_symbols if is_crypto_symbol(symbol)]
        prices: dict[str, Decimal] = {}

        async with httpx.AsyncClient(timeout=15) as client:
            if equities:
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
                prices.update(
                    {
                        symbol: to_decimal(data["p"])
                        for symbol, data in payload.items()
                        if data.get("p") is not None
                    }
                )

            if crypto:
                response = await client.get(
                    f"{settings.alpaca_data_url}/v1beta3/crypto/us/latest/trades",
                    headers=self._headers(),
                    params={"symbols": ",".join(crypto)},
                )
                if response.status_code >= 400:
                    raise MarketDataError(response.text)
                payload = response.json().get("trades", {})
                prices.update(
                    {
                        symbol: to_decimal(data["p"])
                        for symbol, data in payload.items()
                        if data.get("p") is not None
                    }
                )

        return prices
