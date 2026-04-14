#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

import httpx


def signup_user(client: httpx.Client, base_url: str, username: str) -> dict:
    response = client.post(f"{base_url}/v1/signup", json={"username": username})
    response.raise_for_status()
    return response.json()


def create_agent(
    client: httpx.Client,
    base_url: str,
    account_api_key: str,
    name: str,
    trading_mode: str,
    starting_cash: float = 10000,
) -> dict:
    response = client.post(
        f"{base_url}/v1/account/agents",
        json={
            "name": name,
            "starting_cash": starting_cash,
            "trading_mode": trading_mode,
        },
        headers={"Authorization": f"Bearer {account_api_key}"},
    )
    response.raise_for_status()
    return response.json()


def report_executions(
    client: httpx.Client, base_url: str, agent_api_key: str, executions: list[dict]
) -> dict:
    response = client.post(
        f"{base_url}/v1/executions",
        json={"executions": executions},
        headers={"Authorization": f"Bearer {agent_api_key}"},
    )
    response.raise_for_status()
    return response.json()


def iso(minutes_ago: int) -> str:
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return timestamp.isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Bridgewood with demo accounts, agents, and reported executions."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    suffix = int(datetime.now(timezone.utc).timestamp())
    with httpx.Client(timeout=30) as client:
        ben = signup_user(client, args.base_url, f"ben-{suffix}")
        matt = signup_user(client, args.base_url, f"matt-{suffix}")

        agents = [
            create_agent(
                client,
                args.base_url,
                ben["account_api_key"],
                "GPT 5.4",
                "paper",
            ),
            create_agent(
                client,
                args.base_url,
                ben["account_api_key"],
                "Claude Opus 4.6",
                "live",
            ),
            create_agent(
                client,
                args.base_url,
                matt["account_api_key"],
                "Gemini 3.1 Pro",
                "paper",
            ),
        ]

        report_executions(
            client,
            args.base_url,
            agents[0]["api_key"],
            [
                {
                    "external_order_id": f"gpt-aapl-{suffix}-1",
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": 3.2,
                    "price": 187.52,
                    "executed_at": iso(120),
                },
                {
                    "external_order_id": f"gpt-nvda-{suffix}-2",
                    "symbol": "NVDA",
                    "side": "buy",
                    "quantity": 0.75,
                    "price": 906.11,
                    "executed_at": iso(105),
                },
            ],
        )
        report_executions(
            client,
            args.base_url,
            agents[1]["api_key"],
            [
                {
                    "external_order_id": f"claude-msft-{suffix}-1",
                    "symbol": "MSFT",
                    "side": "buy",
                    "quantity": 1.6,
                    "price": 421.23,
                    "executed_at": iso(90),
                },
                {
                    "external_order_id": f"claude-meta-{suffix}-2",
                    "symbol": "META",
                    "side": "buy",
                    "quantity": 1.1,
                    "price": 514.90,
                    "executed_at": iso(75),
                },
            ],
        )
        report_executions(
            client,
            args.base_url,
            agents[2]["api_key"],
            [
                {
                    "external_order_id": f"gemini-tsla-{suffix}-1",
                    "symbol": "TSLA",
                    "side": "buy",
                    "quantity": 4.0,
                    "price": 171.84,
                    "executed_at": iso(60),
                },
                {
                    "external_order_id": f"gemini-aapl-{suffix}-2",
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": 1.5,
                    "price": 187.52,
                    "executed_at": iso(45),
                },
                {
                    "external_order_id": f"gemini-tsla-{suffix}-3",
                    "symbol": "TSLA",
                    "side": "sell",
                    "quantity": 1.0,
                    "price": 176.24,
                    "executed_at": iso(30),
                },
            ],
        )

        print(json.dumps({"seeded_agents": agents}, indent=2))


if __name__ == "__main__":
    main()
