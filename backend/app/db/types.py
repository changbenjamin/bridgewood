from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

from app.core.time import normalize_utc


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(DateTime(timezone=False))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None

        normalized = normalize_utc(value)
        if dialect.name == "sqlite":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return normalize_utc(value)
