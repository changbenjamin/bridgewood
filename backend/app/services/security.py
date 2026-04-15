from __future__ import annotations

import hashlib
import secrets


def generate_agent_api_key() -> str:
    return f"bgw_{secrets.token_urlsafe(24)}"


def generate_account_api_key() -> str:
    return f"bga_{secrets.token_urlsafe(24)}"


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
