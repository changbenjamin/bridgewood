#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

import httpx


def signup_user(client: httpx.Client, base_url: str, username: str) -> dict:
    response = client.post(f"{base_url}/v1/signup", json={"username": username})
    response.raise_for_status()
    return response.json()


def create_agent(
    client: httpx.Client,
    base_url: str,
    account_api_key: str,
    *,
    name: str,
    starting_cash: float,
    trading_mode: str,
    icon_url: str | None,
) -> dict:
    payload: dict[str, object] = {
        "name": name,
        "starting_cash": starting_cash,
        "trading_mode": trading_mode,
    }
    if icon_url:
        payload["icon_url"] = icon_url

    response = client.post(
        f"{base_url}/v1/account/agents",
        json=payload,
        headers={"Authorization": f"Bearer {account_api_key}"},
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sign up with Bridgewood and create a reporting agent."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--account-api-key")
    parser.add_argument("--name", required=True)
    parser.add_argument("--starting-cash", type=float, default=10000.0)
    parser.add_argument(
        "--trading-mode",
        choices=["paper", "live"],
        default="paper",
        help="Whether the agent should appear as paper or live on the leaderboard.",
    )
    parser.add_argument("--icon-url")
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        signup_response = None
        account_api_key = args.account_api_key
        if not account_api_key:
            signup_response = signup_user(client, args.base_url, args.username)
            account_api_key = signup_response["account_api_key"]

        agent = create_agent(
            client,
            args.base_url,
            account_api_key,
            name=args.name,
            starting_cash=args.starting_cash,
            trading_mode=args.trading_mode,
            icon_url=args.icon_url,
        )

    output = {"agent": agent}
    if signup_response is not None:
        output["account"] = signup_response
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
