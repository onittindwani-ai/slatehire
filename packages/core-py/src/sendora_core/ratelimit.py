"""In memory token bucket rate limiter (single process, which fits the single tenant design)."""

from __future__ import annotations

import time
from collections.abc import Callable


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: float):
        super().__init__(f"Too many requests. Try again in {retry_after:.1f} seconds.")
        self.retry_after = retry_after


class TokenBucket:
    """Keeps at most `max_keys` buckets, so a client that sends a new key on every request cannot grow the memory without limit.
    When the table is full, buckets that have refilled completely are dropped first (they are the same as a new one), then the oldest."""

    def __init__(self, capacity: int, refill_per_sec: float, clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000):
        self.capacity, self.refill, self.clock, self.max_keys = capacity, refill_per_sec, clock, max_keys
        self._tokens: dict[str, tuple[float, float]] = {}

    def _make_room(self, now: float) -> None:
        if len(self._tokens) < self.max_keys:
            return
        full = [k for k, (t, last) in self._tokens.items() if t + (now - last) * self.refill >= self.capacity]
        for k in full:
            del self._tokens[k]
        if len(self._tokens) >= self.max_keys:
            for k, _ in sorted(self._tokens.items(), key=lambda kv: kv[1][1])[: max(1, self.max_keys // 10)]:
                del self._tokens[k]

    def check(self, key: str, cost: float = 1.0) -> None:
        now = self.clock()
        key = key[:256]  # a key chosen by a client cannot be longer than this
        tokens, last = self._tokens.get(key, (float(self.capacity), now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        if tokens < cost:
            raise RateLimitExceeded((cost - tokens) / self.refill if self.refill else 60.0)
        if key not in self._tokens:
            self._make_room(now)
        self._tokens[key] = (tokens - cost, now)
