"""In memory token bucket rate limiter (single process, which fits the single tenant design)."""

from __future__ import annotations

import time
from collections.abc import Callable


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: float):
        super().__init__(f"Too many requests. Try again in {retry_after:.1f} seconds.")
        self.retry_after = retry_after


class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float, clock: Callable[[], float] = time.monotonic):
        self.capacity, self.refill, self.clock = capacity, refill_per_sec, clock
        self._tokens: dict[str, tuple[float, float]] = {}

    def check(self, key: str, cost: float = 1.0) -> None:
        now = self.clock()
        tokens, last = self._tokens.get(key, (float(self.capacity), now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        if tokens < cost:
            raise RateLimitExceeded((cost - tokens) / self.refill if self.refill else 60.0)
        self._tokens[key] = (tokens - cost, now)
