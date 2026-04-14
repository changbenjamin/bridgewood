from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime

from app.core.errors import BridgewoodError
from app.core.time import normalize_utc


@dataclass(frozen=True)
class PageCursor:
    executed_at: datetime
    created_at: datetime
    row_id: str


def encode_cursor(*, executed_at: datetime, created_at: datetime, row_id: str) -> str:
    payload = {
        "executed_at": normalize_utc(executed_at).isoformat(),
        "created_at": normalize_utc(created_at).isoformat(),
        "row_id": row_id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def decode_cursor(value: str) -> PageCursor:
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))
        return PageCursor(
            executed_at=normalize_utc(datetime.fromisoformat(payload["executed_at"])),
            created_at=normalize_utc(datetime.fromisoformat(payload["created_at"])),
            row_id=str(payload["row_id"]),
        )
    except Exception as exc:  # pragma: no cover - defensive parsing
        raise BridgewoodError(
            status_code=400,
            detail="Invalid pagination cursor.",
            code="INVALID_CURSOR",
        ) from exc
