from collections import deque
from dataclasses import dataclass
import math
from threading import Lock
import time


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("Rate limit must be greater than zero.")

        if self.window_seconds <= 0:
            raise ValueError("Rate-limit window must be greater than zero.")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    rule_name: str | None = None


class InMemorySlidingWindowRateLimiter:
    """Thread-safe visitor and IP rate limits for a single API instance."""

    def __init__(
        self,
        visitor_rules: tuple[RateLimitRule, ...],
        ip_rules: tuple[RateLimitRule, ...],
        enabled: bool = True,
    ) -> None:
        self.visitor_rules = visitor_rules
        self.ip_rules = ip_rules
        self.enabled = enabled
        self._events: dict[tuple[str, str, str], deque[float]] = {}
        self._last_seen: dict[tuple[str, str, str], float] = {}
        self._lock = Lock()
        self._checks_since_cleanup = 0
        self._max_window_seconds = max(
            (
                rule.window_seconds
                for rule in (*visitor_rules, *ip_rules)
            ),
            default=0,
        )

    def check(
        self,
        visitor_id: str,
        ip_address: str,
        now: float | None = None,
    ) -> RateLimitDecision:
        if not self.enabled:
            return RateLimitDecision(allowed=True)

        current_time = time.monotonic() if now is None else now
        identities = (
            ("visitor", visitor_id, self.visitor_rules),
            ("ip", ip_address, self.ip_rules),
        )

        with self._lock:
            self._checks_since_cleanup += 1

            if self._checks_since_cleanup >= 500:
                self._cleanup_stale_keys(current_time)
                self._checks_since_cleanup = 0

            applicable_buckets = []
            blocked_decisions = []

            for scope, identity, rules in identities:
                for rule in rules:
                    key = (scope, identity, rule.name)
                    bucket = self._events.setdefault(key, deque())
                    cutoff = current_time - rule.window_seconds

                    while bucket and bucket[0] <= cutoff:
                        bucket.popleft()

                    self._last_seen[key] = current_time
                    applicable_buckets.append((bucket, rule))

                    if len(bucket) >= rule.limit:
                        retry_after = max(
                            1,
                            math.ceil(
                                rule.window_seconds
                                - (current_time - bucket[0])
                            ),
                        )
                        blocked_decisions.append(
                            RateLimitDecision(
                                allowed=False,
                                retry_after_seconds=retry_after,
                                rule_name=f"{scope}_{rule.name}",
                            )
                        )

            if blocked_decisions:
                return max(
                    blocked_decisions,
                    key=lambda decision: decision.retry_after_seconds,
                )

            for bucket, _ in applicable_buckets:
                bucket.append(current_time)

        return RateLimitDecision(allowed=True)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._last_seen.clear()
            self._checks_since_cleanup = 0

    def _cleanup_stale_keys(self, current_time: float) -> None:
        if self._max_window_seconds <= 0:
            return

        cutoff = current_time - self._max_window_seconds
        stale_keys = [
            key
            for key, last_seen in self._last_seen.items()
            if last_seen <= cutoff
        ]

        for key in stale_keys:
            self._events.pop(key, None)
            self._last_seen.pop(key, None)
