"""Rate limiting. ``InMemoryRateLimiter`` is process-local (tests, single node);
``RedisRateLimiter`` (integrations/redis_rate_limit.py) is shared across workers."""
from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol

from ..shared.clock import Clock
from ..shared.errors import RateLimited


@dataclass(frozen=True)
class Policy:
    limit: int
    window_s: int


# Sensitive endpoints get tight limits (spec section 49).
POLICIES: dict[str, Policy] = {
    "login": Policy(10, 60), "otp": Policy(5, 300), "password_reset": Policy(5, 900),
    "payment": Policy(30, 60), "kyc": Policy(5, 600), "webhook": Policy(300, 60),
    "public_search": Policy(60, 60), "default": Policy(120, 60),
}


class RateLimiter(Protocol):
    def check(self, bucket: str, identity: str) -> None: ...


class InMemoryRateLimiter:
    """Sliding-window log limiter."""

    def __init__(self, clock: Clock, policies: dict[str, Policy] | None = None):
        self._clock, self._policies = clock, policies or POLICIES
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, bucket: str, identity: str) -> None:
        policy = self._policies.get(bucket, self._policies["default"])
        now = self._clock.now().timestamp()
        with self._lock:
            q = self._hits[(bucket, identity)]
            while q and q[0] <= now - policy.window_s:
                q.popleft()
            if len(q) >= policy.limit:
                retry = int(q[0] + policy.window_s - now) + 1
                raise RateLimited("too many requests", details={"retry_after_s": retry, "bucket": bucket})
            q.append(now)
