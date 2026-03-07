"""Token bucket rate limiter for WebSocket connections.

Default: 20 messages per 60 seconds per connection.
Configurable in aether_config.yaml as websocket.rate_limit_per_minute.
"""

import time
from collections import defaultdict

from loguru import logger

# {connection_id: {"tokens": float, "last_refill": float}}
_buckets: dict[str, dict] = defaultdict(lambda: {"tokens": 20.0, "last_refill": time.time()})

RATE_LIMIT = 20  # messages
WINDOW_SEC = 60.0  # per minute


def check_rate_limit(connection_id: str) -> bool:
    """Return True if the message is allowed, False if rate limited.

    Uses token bucket: refills at RATE_LIMIT/WINDOW_SEC tokens per second.
    """
    now = time.time()
    bucket = _buckets[connection_id]

    # Refill tokens based on elapsed time
    elapsed = now - bucket["last_refill"]
    refill = elapsed * (RATE_LIMIT / WINDOW_SEC)
    bucket["tokens"] = min(RATE_LIMIT, bucket["tokens"] + refill)
    bucket["last_refill"] = now

    if bucket["tokens"] >= 1.0:
        bucket["tokens"] -= 1.0
        return True

    logger.warning(f"RateLimit: connection {connection_id[:8]} throttled")
    return False


def clear_bucket(connection_id: str) -> None:
    """Call when a connection closes."""
    _buckets.pop(connection_id, None)
