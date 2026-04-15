#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report a cash deposit or withdrawal for a Bridgewood agent."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--account-api-key", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument(
        "--kind",
        choices=["deposit", "withdrawal"],
        default="deposit",
    )
    parser.add_argument("--amount", type=float, required=True)
    parser.add_argument(
        "--effective-at",
        default=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    parser.add_argument("--note")
    parser.add_argument("--external-id")
    args = parser.parse_args()

    payload = {
        "kind": args.kind,
        "amount": args.amount,
        "effective_at": args.effective_at,
    }
    if args.note:
        payload["note"] = args.note
    if args.external_id:
        payload["external_id"] = args.external_id

    response = httpx.post(
        f"{args.base_url}/v1/account/agents/{args.agent_id}/cash-adjustments",
        json=payload,
        headers={"Authorization": f"Bearer {args.account_api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
