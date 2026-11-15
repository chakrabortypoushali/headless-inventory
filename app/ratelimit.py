
# app/ratelimit.py
# A tiny in-memory sliding-window rate limiter

import time
from collections import defaultdict, deque


class RateLimiter:
    """
    Allow at most `max_events` requests per `window_seconds`
    for each unique key.

    Uses in-memory storage, so limits apply per process.

    For multiple server processes or multiple servers,
    use a shared store such as Redis instead.
    """

    def __init__(
        self,
        max_events: int,
        window_seconds: int
    ):
        self.max_events = max_events
        self.window = window_seconds

        self._events: dict[str, deque] = defaultdict(deque)

    # --------------------------------------------------
    # Get Recent Events
    # --------------------------------------------------

    def _recent(self, key: str) -> deque:
        """
        Return events within the current sliding window.

        Remove expired events from the queue.
        """

        queue = self._events[key]

        cutoff = time.monotonic() - self.window

        while queue and queue[0] <= cutoff:
            queue.popleft()

        return queue

    # --------------------------------------------------
    # Check Rate Limit
    # --------------------------------------------------

    def is_blocked(self, key: str) -> bool:
        """
        Check whether the key has exceeded its rate limit.

        Returns:
            True  -> Request should be blocked.
            False -> Request is allowed.
        """

        return len(self._recent(key)) >= self.max_events

    # --------------------------------------------------
    # Record Event
    # --------------------------------------------------

    def record(self, key: str) -> None:
        """
        Record a new event for the given key.

        Also performs basic memory cleanup when the
        number of tracked keys exceeds 10,000.
        """

        if len(self._events) > 10_000:

            for k in [
                k for k in self._events
                if not self._recent(k)
            ]:
                del self._events[k]

        self._events[key].append(time.monotonic())

    # --------------------------------------------------
    # Reset Rate Limit
    # --------------------------------------------------

    def reset(self, key: str) -> None:
        """
        Remove all recorded events for a specific key.
        """

        self._events.pop(key, None)
