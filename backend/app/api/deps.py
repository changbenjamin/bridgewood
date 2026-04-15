from __future__ import annotations

from fastapi import Depends, Header, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BridgewoodError
from app.db.session import get_db
from app.models.entities import Agent, User
from app.services.security import hash_api_key


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise BridgewoodError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            code="MISSING_BEARER_TOKEN",
        )
    return authorization.split(" ", 1)[1].strip()


def get_current_agent(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Agent:
    token = _extract_bearer_token(authorization)
    api_key_hash = hash_api_key(token)
    agent = db.scalar(select(Agent).where(Agent.api_key_hash == api_key_hash))
    if agent is None:
        raise BridgewoodError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            code="INVALID_API_KEY",
        )
    if not agent.is_active:
        raise BridgewoodError(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent is inactive.",
            code="AGENT_INACTIVE",
        )
    return agent


def get_current_account_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_bearer_token(authorization)
    api_key_hash = hash_api_key(token)
    user = db.scalar(select(User).where(User.account_api_key_hash == api_key_hash))
    if user is None:
        raise BridgewoodError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid account API key.",
            code="INVALID_ACCOUNT_API_KEY",
        )
    return user
