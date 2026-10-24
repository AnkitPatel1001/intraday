"""In-memory sliding-window rate limiter (no external dependencies)."""

from __future__ import annotations

import math
import time
from collections import deque


class SlidingWindowLimiter:
    """Fixed-window-fallback sliding window: timestamps deque per key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, limit: int, window: float = 60.0) -> tuple[bool, int]:
        """Record a hit for `key`. Returns (allowed, retry_after_seconds)."""
        if limit <= 0:
            return True, 0
        now = time.monotonic()
        dq = self._hits.setdefault(key, deque())
        cutoff = now - window
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= limit:
            retry = int(math.ceil(dq[0] + window - now))
            return False, max(retry, 1)
        dq.append(now)
        return True, 0

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()
