from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from app.core.errors import BridgewoodError


class InMemoryRateLimiter:
    def __init__(self, rules: dict[str, tuple[int, int]]) -> None:
        self.rules = rules
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, scope: str, key: str, *, detail: str) -> None:
        if scope not in self.rules:
            return

        limit, window_seconds = self.rules[scope]
        now = time.monotonic()
        bucket_key = (scope, key)

        async with self._lock:
            bucket = self._buckets[bucket_key]
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise BridgewoodError(
                    status_code=429,
                    detail=detail,
                    code="RATE_LIMITED",
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.append(now)
