"""Metrics collection — tracks runtime performance counters.

In-memory counters reset on restart. Exposed via /health endpoint.
"""

import time
from dataclasses import dataclass, field

from loguru import logger

_start_time = time.time()


@dataclass
class Metrics:
    """Runtime performance counters."""

    turn_count: int = 0
    token_usage: dict[str, int] = field(
        default_factory=lambda: {
            "fast": 0,
            "claude": 0,
            "gemini": 0,
        }
    )
    tool_call_count: int = 0
    tool_errors: int = 0
    response_latencies: list[float] = field(default_factory=list)
    ws_messages_received: int = 0
    ws_messages_sent: int = 0
    memory_searches: int = 0

    def record_turn(self) -> None:
        """Increment turn count."""
        self.turn_count += 1

    def record_tokens(self, tier: str, count: int) -> None:
        """Record token usage for a tier."""
        tier_key = tier.lower()
        if tier_key not in self.token_usage:
            self.token_usage[tier_key] = 0
        self.token_usage[tier_key] += count

    def record_tool_call(self, success: bool = True) -> None:
        """Record a tool call."""
        self.tool_call_count += 1
        if not success:
            self.tool_errors += 1

    def record_response_latency(self, latency_ms: float) -> None:
        """Record LLM response latency in ms. Keeps last 100."""
        self.response_latencies.append(latency_ms)
        if len(self.response_latencies) > 100:
            self.response_latencies = self.response_latencies[-100:]

    def record_ws_message(self, direction: str) -> None:
        """Record WebSocket message (direction: 'in' or 'out')."""
        if direction == "in":
            self.ws_messages_received += 1
        else:
            self.ws_messages_sent += 1

    def record_memory_search(self) -> None:
        """Record a memory search operation."""
        self.memory_searches += 1

    def avg_response_latency_ms(self) -> float:
        """Average response latency in ms."""
        if not self.response_latencies:
            return 0.0
        return round(sum(self.response_latencies) / len(self.response_latencies), 1)

    def to_dict(self) -> dict:
        """Serialize to dict for health endpoint."""
        return {
            "uptime_seconds": round(time.time() - _start_time, 1),
            "turn_count": self.turn_count,
            "token_usage": dict(self.token_usage),
            "tool_calls": self.tool_call_count,
            "tool_errors": self.tool_errors,
            "avg_response_latency_ms": self.avg_response_latency_ms(),
            "ws_messages_received": self.ws_messages_received,
            "ws_messages_sent": self.ws_messages_sent,
            "memory_searches": self.memory_searches,
        }


# Module-level singleton
_metrics: Metrics | None = None


def get_metrics() -> Metrics:
    """Get the global metrics singleton."""
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics


def get_metrics_summary() -> dict:
    """Get metrics as a dict (for health endpoint)."""
    return get_metrics().to_dict()


async def log_metrics_periodically(interval_seconds: int = 3600) -> None:
    """Background task to log metrics every interval (default: 1 hour)."""
    import asyncio

    while True:
        await asyncio.sleep(interval_seconds)
        m = get_metrics()
        logger.info(
            f"Metrics: turns={m.turn_count}, tools={m.tool_call_count}, "
            f"avg_latency={m.avg_response_latency_ms()}ms, "
            f"tokens={m.token_usage}"
        )
