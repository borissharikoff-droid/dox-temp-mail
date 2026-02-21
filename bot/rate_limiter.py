"""In-memory per-user rate limiter with TTL auto-cleanup."""
import threading
import time
from collections import defaultdict

from config import RATE_LIMIT_CREATE, RATE_LIMIT_REFRESH, RATE_LIMIT_GENERAL

_lock = threading.Lock()
_buckets: dict[str, list[float]] = defaultdict(list)

_LAST_CLEANUP = 0.0
_CLEANUP_INTERVAL = 300  # purge stale entries every 5 min

LIMITS = {
    "create_mail": (RATE_LIMIT_CREATE, 3600),
    "refresh":     (RATE_LIMIT_REFRESH, 60),
    "general":     (RATE_LIMIT_GENERAL, 60),
}


def _cleanup_if_needed():
    global _LAST_CLEANUP
    now = time.monotonic()
    if now - _LAST_CLEANUP < _CLEANUP_INTERVAL:
        return
    _LAST_CLEANUP = now
    stale_keys = [k for k, v in _buckets.items() if not v]
    for k in stale_keys:
        _buckets.pop(k, None)


def is_allowed(user_id: str, action: str) -> bool:
    """Return True if the action is within rate limits, False if throttled."""
    max_count, window = LIMITS.get(action, LIMITS["general"])
    key = f"{user_id}:{action}"
    now = time.monotonic()
    cutoff = now - window

    with _lock:
        _cleanup_if_needed()
        timestamps = _buckets[key]
        _buckets[key] = [t for t in timestamps if t > cutoff]
        if len(_buckets[key]) >= max_count:
            return False
        _buckets[key].append(now)
        return True
