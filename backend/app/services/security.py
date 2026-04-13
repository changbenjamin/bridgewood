from __future__ import annotations

import hashlib
import secrets

from cryptography.fernet import Fernet

from app.core.config import get_settings


settings = get_settings()
fernet = Fernet(settings.fernet_key.encode())


def generate_agent_api_key() -> str:
    return f"bgw_{secrets.token_urlsafe(24)}"


def generate_account_api_key() -> str:
    return f"bga_{secrets.token_urlsafe(24)}"


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def encrypt_secret(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()
