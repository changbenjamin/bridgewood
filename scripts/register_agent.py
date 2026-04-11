#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a new trading agent.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--admin-token", default="bridgewood-admin-token")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--starting-cash", type=float, default=10000.0)
    parser.add_argument("--icon-url")
    args = parser.parse_args()

    payload = {
        "user_id": args.user_id,
        "name": args.name,
        "starting_cash": args.starting_cash,
        "icon_url": args.icon_url,
    }

    response = httpx.post(
        f"{args.base_url}/v1/agents",
        json=payload,
        headers={"X-Admin-Token": args.admin_token},
        timeout=30,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
