"""EventBus — pub/sub backbone for async event-driven flows between modules.

Supports backpressure via per-event-type inflight limits (asyncio.Semaphore).
When inflight count exceeds limit, new events are dropped with a warning.
"""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable

from loguru import logger

from src.shared.types import EventType, AetherEvent

HandlerType = Callable[[AetherEvent], Awaitable[None]]


class EventBus:
    def __init__(self):
        self._handlers: dict[EventType, list[HandlerType]] = defaultdict(list)
        self._inflight_limits: dict[EventType, int] = {}
        self._inflight_counts: dict[EventType, int] = defaultdict(int)
        self._dropped_counts: dict[EventType, int] = defaultdict(int)

    def subscribe(self, event_type: EventType, handler: HandlerType) -> None:
        self._handlers[event_type].append(handler)
        logger.debug(f"EventBus: {handler.__module__} subscribed to {event_type}")

    def unsubscribe(self, event_type: EventType, handler: HandlerType) -> None:
        """Remove a handler. No-op if handler is not subscribed."""
        handlers = self._handlers.get(event_type, [])
        try:
            handlers.remove(handler)
            logger.debug(f"EventBus: {handler.__module__} unsubscribed from {event_type}")
        except ValueError:
            pass  # Handler not in list — nothing to remove

    def set_max_inflight(self, event_type: EventType, limit: int) -> None:
        """Set max concurrent inflight events for a given type.

        When inflight count exceeds limit, new events are dropped with a warning.
        Default: no limit (backwards compatible).
        """
        self._inflight_limits[event_type] = limit
        logger.info(f"EventBus: backpressure set for {event_type} — max {limit} inflight")

    async def publish(self, event: AetherEvent) -> None:
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            logger.debug(f"EventBus: no handlers for {event.type}")
            return

        # Backpressure check
        limit = self._inflight_limits.get(event.type)
        if limit is not None and self._inflight_counts[event.type] >= limit:
            self._dropped_counts[event.type] += 1
            dropped = self._dropped_counts[event.type]
            if dropped <= 5 or dropped % 50 == 0:
                logger.warning(
                    f"EventBus: dropping {event.type} — {self._inflight_counts[event.type]}/{limit} "
                    f"inflight (total dropped: {dropped})"
                )
            return

        self._inflight_counts[event.type] += 1
        try:
            tasks = [asyncio.create_task(h(event)) for h in handlers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result, handler in zip(results, handlers, strict=False):
                if isinstance(result, Exception):
                    logger.error(f"EventBus: handler {handler.__name__} raised {result} for event {event.type}")
        finally:
            self._inflight_counts[event.type] -= 1

    def get_dropped_count(self, event_type: EventType) -> int:
        """Get the total number of dropped events for a given type."""
        return self._dropped_counts.get(event_type, 0)

    def get_inflight_count(self, event_type: EventType) -> int:
        """Get the current number of inflight events for a given type."""
        return self._inflight_counts.get(event_type, 0)


# Singleton instance — import this everywhere
event_bus = EventBus()
