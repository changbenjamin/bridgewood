#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time

import httpx


def create_user(
    client: httpx.Client, base_url: str, admin_token: str, username: str
) -> dict:
    response = client.post(
        f"{base_url}/v1/users",
        json={
            "username": username,
            "alpaca_api_key": f"mock-{username}-key",
            "alpaca_secret_key": f"mock-{username}-secret",
            "alpaca_base_url": "https://paper-api.alpaca.markets",
        },
        headers={"X-Admin-Token": admin_token},
    )
    response.raise_for_status()
    return response.json()


def create_agent(
    client: httpx.Client, base_url: str, admin_token: str, user_id: str, name: str
) -> dict:
    response = client.post(
        f"{base_url}/v1/agents",
        json={
            "user_id": user_id,
            "name": name,
            "starting_cash": 10000,
        },
        headers={"X-Admin-Token": admin_token},
    )
    response.raise_for_status()
    return response.json()


def submit_cycle(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    trades: list[dict],
    rationale: str,
    cost: float,
) -> None:
    response = client.post(
        f"{base_url}/v1/trades",
        json={
            "trades": trades,
            "rationale": rationale,
            "cycle_cost": cost,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the app with demo users, agents, and trades."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--admin-token", default="bridgewood-admin-token")
    args = parser.parse_args()

    suffix = int(time.time())
    with httpx.Client(timeout=30) as client:
        ben = create_user(client, args.base_url, args.admin_token, f"ben-{suffix}")
        matt = create_user(client, args.base_url, args.admin_token, f"matt-{suffix}")

        agents = [
            create_agent(
                client, args.base_url, args.admin_token, ben["user_id"], "GPT 5.4"
            ),
            create_agent(
                client,
                args.base_url,
                args.admin_token,
                ben["user_id"],
                "Claude Opus 4.6",
            ),
            create_agent(
                client,
                args.base_url,
                args.admin_token,
                matt["user_id"],
                "Gemini 3.1 Pro",
            ),
        ]

        orders = [
            (
                agents[0]["api_key"],
                [
                    {
                        "symbol": "AAPL",
                        "side": "buy",
                        "amount_dollars": 600,
                        "client_order_id": f"aapl-{suffix}-1",
                    },
                    {
                        "symbol": "NVDA",
                        "side": "buy",
                        "amount_dollars": 900,
                        "client_order_id": f"nvda-{suffix}-2",
                    },
                ],
                "Leaning into liquid large-cap names with strong relative strength.",
                184.2,
            ),
            (
                agents[1]["api_key"],
                [
                    {
                        "symbol": "MSFT",
                        "side": "buy",
                        "amount_dollars": 750,
                        "client_order_id": f"msft-{suffix}-1",
                    },
                    {
                        "symbol": "META",
                        "side": "buy",
                        "amount_dollars": 520,
                        "client_order_id": f"meta-{suffix}-2",
                    },
                ],
                "Favoring software and platform cash flows while keeping dry powder.",
                146.4,
            ),
            (
                agents[2]["api_key"],
                [
                    {
                        "symbol": "TSLA",
                        "side": "buy",
                        "amount_dollars": 700,
                        "client_order_id": f"tsla-{suffix}-1",
                    },
                    {
                        "symbol": "AAPL",
                        "side": "buy",
                        "amount_dollars": 350,
                        "client_order_id": f"aapl-{suffix}-3",
                    },
                ],
                "Taking a momentum sleeve with a small quality hedge.",
                92.8,
            ),
            (
                agents[2]["api_key"],
                [
                    {
                        "symbol": "MSFT",
                        "side": "buy",
                        "amount_dollars": 220,
                        "client_order_id": f"msft-{suffix}-3",
                    },
                ],
                "Adding a small software position after the initial momentum sleeve.",
                31.2,
            ),
        ]

        for api_key, trades, rationale, cost in orders:
            submit_cycle(client, args.base_url, api_key, trades, rationale, cost)

        print(json.dumps({"seeded_agents": agents}, indent=2))


if __name__ == "__main__":
    main()
