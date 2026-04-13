#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time

import httpx


def create_mock_agent(client: httpx.Client, base_url: str, name: str) -> dict:
    response = client.post(
        f"{base_url}/v1/dev/mock-agent",
        json={"name": name},
    )
    response.raise_for_status()
    return response.json()


def get_portfolio(client: httpx.Client, base_url: str, api_key: str) -> dict:
    response = client.get(
        f"{base_url}/v1/portfolio",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response.raise_for_status()
    return response.json()


def has_position(
    client: httpx.Client, base_url: str, api_key: str, symbol: str
) -> bool:
    portfolio = get_portfolio(client, base_url, api_key)
    return any(
        position["symbol"] == symbol and position["quantity"] > 0
        for position in portfolio["positions"]
    )


def submit_trade(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    *,
    symbol: str,
    side: str,
    amount_dollars: float | None = None,
    sell_all: bool = False,
    rationale: str,
) -> dict:
    payload: dict[str, object] = {
        "symbol": symbol,
        "side": side,
        "rationale": rationale,
        "cycle_cost": 0,
    }
    if amount_dollars is not None:
        payload["amount_dollars"] = amount_dollars
    if sell_all:
        payload["sell_all"] = True

    response = client.post(
        f"{base_url}/v1/trade",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a simple mock AAPL trading bot against Bridgewood."
    )
    parser.add_argument(
        "--base-url", default=os.getenv("BRIDGEWOOD_BASE_URL", "http://localhost:8000")
    )
    parser.add_argument("--api-key")
    parser.add_argument("--name", default="AAPL Bot")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--buy-amount", type=float, default=500.0)
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=600,
        help="How long to wait between buy and sell actions.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Number of buy/sell cycles to run. Use 0 to loop forever.",
    )
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        api_key = args.api_key or os.getenv("BRIDGEWOOD_AGENT_API_KEY")
        if not api_key:
            bootstrap = create_mock_agent(client, args.base_url, args.name)
            api_key = bootstrap["api_key"]
            print("Created mock agent:")
            print(json.dumps(bootstrap, indent=2))

        holding = has_position(client, args.base_url, api_key, args.symbol)
        if holding:
            print(
                f"Detected an existing {args.symbol} position. "
                "Continuing from the sell side of the cycle."
            )
        else:
            buy_result = submit_trade(
                client,
                args.base_url,
                api_key,
                symbol=args.symbol,
                side="buy",
                amount_dollars=args.buy_amount,
                rationale=f"Buying {args.symbol} for the timed mock strategy.",
            )
            print("Bought:")
            print(json.dumps(buy_result, indent=2))
            holding = True

        completed_cycles = 0
        while args.cycles == 0 or completed_cycles < args.cycles:
            time.sleep(args.hold_seconds)

            if holding:
                sell_result = submit_trade(
                    client,
                    args.base_url,
                    api_key,
                    symbol=args.symbol,
                    side="sell",
                    sell_all=True,
                    rationale=(
                        f"Selling the full {args.symbol} position for the timed "
                        "mock strategy."
                    ),
                )
                print("Sold:")
                print(json.dumps(sell_result, indent=2))
                holding = False
                completed_cycles += 1
            else:
                buy_result = submit_trade(
                    client,
                    args.base_url,
                    api_key,
                    symbol=args.symbol,
                    side="buy",
                    amount_dollars=args.buy_amount,
                    rationale=f"Buying {args.symbol} for the timed mock strategy.",
                )
                print("Bought:")
                print(json.dumps(buy_result, indent=2))
                holding = True


if __name__ == "__main__":
    main()
