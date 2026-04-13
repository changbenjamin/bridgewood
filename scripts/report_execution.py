#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report a filled execution to Bridgewood."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--external-order-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", choices=["buy", "sell"], required=True)
    parser.add_argument("--quantity", type=float, required=True)
    parser.add_argument("--price", type=float, required=True)
    parser.add_argument("--fees", type=float, default=0.0)
    parser.add_argument(
        "--executed-at",
        default=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    args = parser.parse_args()

    payload = {
        "executions": [
            {
                "external_order_id": args.external_order_id,
                "symbol": args.symbol,
                "side": args.side,
                "quantity": args.quantity,
                "price": args.price,
                "fees": args.fees,
                "executed_at": args.executed_at,
            }
        ]
    }

    response = httpx.post(
        f"{args.base_url}/v1/executions",
        json=payload,
        headers={"Authorization": f"Bearer {args.api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
