"""Sign in throttling. Three limits, and a short memory of who the real owner is, plus a per browser note for a shared address.

1. Per address: every try from one address, whatever email it names.
2. Per address and account: tries at one account from one address (a burst, then one more every 12 seconds).
3. Per account, from anywhere, counting only FAILED tries (a burst, then one more every 30 seconds). It stops guesses that are spread over many
   addresses. An attempt from an address that already signed in successfully as that account in the last 24 hours is never held up by it, so
   someone who only knows the owner's email cannot keep the owner out by failing on purpose from somewhere else.

4. A browser that already signed in as the account carries a signed note (devicetoken.py). Its tries are counted on their own, per browser, and are not held up by the shared
   limits above. This is what keeps the owner able to sign in when every visitor reaches the API as one address (a proxy whose forwarded address is not trusted:
   set FORWARDED_ALLOW_IPS), which would otherwise let one bad try every 10 seconds from anyone shut the owner out.

Residual risk: while an attack on the account is running, a first sign in from a NEW address (a new phone, a new office) waits until the failures
slow down. The per address, and per address and account, limits still apply to everyone, including a known address. The memory is in this process only: a restart
forgets it, and behind a proxy that does not pass the visitor's address on, every visitor looks like the same address.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable

from sendora_core.ratelimit import RateLimitExceeded, TokenBucket

log = logging.getLogger("slatehire.loginguard")

KNOWN_FOR_S = 24 * 3600
MAX_KNOWN = 2048
MAX_KEYS = 10_000
WATCH_S = 24 * 3600  # how far back the "everyone looks like one address" check looks
LOG_EVERY_S = 3600
UNTRUSTED_NOTE = ("The web app passes on each visitor's address, but the API does not trust it, so every visitor looks like the same address and the sign in limits are shared by everyone: one bad try "
                  "from anyone can hold up the owner. Set FORWARDED_ALLOW_IPS on the API service to the address range of the web service (docs/06-DEPLOY-VERCEL.md, docs/07-DEPLOY-RAILWAY.md).")
ONE_ADDRESS_NOTE = ("Every sign in try in the last 24 hours ({tries}, {fails} of them wrong) came from one address. If that is not one person at one desk, your proxy hides the visitors' addresses and the sign in "
                    "limits are shared by everyone. Check FORWARDED_ALLOW_IPS (docs/06-DEPLOY-VERCEL.md, docs/07-DEPLOY-RAILWAY.md). A browser that signed in before is not affected.")


class _Failures:
    """A bucket that is only spent on a failure. `blocked` looks without spending."""

    def __init__(self, capacity: int, refill_per_sec: float, clock: Callable[[], float]):
        self.capacity, self.refill, self.clock = capacity, refill_per_sec, clock
        self._t: dict[str, tuple[float, float]] = {}

    def _tokens(self, key: str, now: float) -> float:
        tokens, last = self._t.get(key, (float(self.capacity), now))
        return min(float(self.capacity), tokens + (now - last) * self.refill)

    def blocked(self, key: str) -> float | None:
        """Seconds to wait, or None when the account may be tried."""
        tokens = self._tokens(key[:256], self.clock())
        return None if tokens >= 1 else (1 - tokens) / self.refill

    def spend(self, key: str) -> None:
        now, key = self.clock(), key[:256]
        if key not in self._t and len(self._t) >= MAX_KEYS:
            full = [k for k in self._t if self._tokens(k, now) >= self.capacity]
            for k in full or sorted(self._t, key=lambda k: self._t[k][1])[: MAX_KEYS // 10]:
                del self._t[k]
        self._t[key] = (max(0.0, self._tokens(key, now) - 1), now)


class LoginGuard:
    def __init__(self, burst: int, clock: Callable[[], float] = time.monotonic, watch_one_address: bool = True):
        self.clock = clock
        self.watch_one_address = watch_one_address  # off in the demo, where one person on one computer is expected
        self._lock = threading.Lock()
        self._ip = TokenBucket(capacity=max(30, burst * 6), refill_per_sec=1 / 3, clock=clock)
        self._pair = TokenBucket(capacity=burst, refill_per_sec=1 / 12, clock=clock)
        self._failures = _Failures(max(20, burst * 4), 1 / 30, clock)
        self._device = TokenBucket(capacity=max(10, burst * 2), refill_per_sec=1 / 10, clock=clock)  # one browser that signed in before, counted on its own
        self._known: OrderedDict[str, float] = OrderedDict()
        self._tries: deque[tuple[float, str]] = deque(maxlen=2000)  # (when, hashed address) of every try, to notice a proxy that hides the visitors
        self._fails: deque[tuple[float, str]] = deque(maxlen=2000)
        self._untrusted_at: float | None = None
        self._logged_at: dict[str, float] = {}

    @staticmethod
    def _known_key(host: str, email: str) -> str:
        return hashlib.sha256(f"{host}|{email}".encode()).hexdigest()  # no address or email is kept in the clear

    def is_known(self, host: str, email: str) -> bool:
        key, now = self._known_key(host, email), self.clock()
        until = self._known.get(key)
        if until is None:
            return False
        if until <= now:
            del self._known[key]
            return False
        return True

    def note_forwarded(self, peer: str, claimed: str) -> None:
        """The web app says the visitor is `claimed`, but the API sees the connection come from `peer`: the API does not trust the forwarded address (FORWARDED_ALLOW_IPS)."""
        if claimed and claimed != peer:
            with self._lock:
                self._untrusted_at = self.clock()
                self._log_once("untrusted", UNTRUSTED_NOTE)

    def _log_once(self, key: str, message: str) -> None:
        now = self.clock()
        if now - self._logged_at.get(key, -LOG_EVERY_S) >= LOG_EVERY_S:
            self._logged_at[key] = now
            log.warning(message)

    def warnings(self) -> list[str]:
        """Plain sentences for the settings page when the limits cannot tell visitors apart. Empty when all is well."""
        with self._lock:
            now, out = self.clock(), []
            if self._untrusted_at is not None and now - self._untrusted_at < WATCH_S:
                out.append(UNTRUSTED_NOTE)
            tries = [h for t, h in self._tries if now - t <= WATCH_S]
            fails = [h for t, h in self._fails if now - t <= WATCH_S]
            if self.watch_one_address and len(tries) >= 10 and len(set(tries)) == 1 and len(fails) >= 3:
                note = ONE_ADDRESS_NOTE.format(tries=len(tries), fails=len(fails))
                out.append(note)
                self._log_once("one_address", note)
            return out

    def check(self, host: str, email: str, device: str | None = None) -> None:
        """Raises RateLimitExceeded when this try must wait. Call before the password is looked at. `device` is the id from a genuine note (devicetoken.py): that browser
        has signed in as this account before, so it is counted on its own and is not held up by the limits that everyone behind one address shares."""
        with self._lock:
            self._tries.append((self.clock(), self._known_key(host, "")))
            if device:
                self._device.check(device)
                return
            self._ip.check(host)
            self._pair.check(f"{host}:{email}")
            wait = None if self.is_known(host, email) else self._failures.blocked(email)
            if wait is not None:
                raise RateLimitExceeded(wait)

    def failed(self, host: str, email: str, device: str | None = None) -> None:
        with self._lock:
            self._fails.append((self.clock(), self._known_key(host, "")))
            if not device:  # a browser that signed in before is held by its own bucket only, so a stranger's guesses cannot spend its tries
                self._failures.spend(email)

    def succeeded(self, host: str, email: str) -> None:
        """Remember that this address signed in as this account. Set only after the password was verified."""
        with self._lock:
            key = self._known_key(host, email)
            self._known.pop(key, None)
            self._known[key] = self.clock() + KNOWN_FOR_S
            while len(self._known) > MAX_KNOWN:
                self._known.popitem(last=False)
