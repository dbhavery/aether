"""Module 01 tests — verify core server meets done criteria."""

import asyncio

import pytest

from src.core.events import EventBus
from src.shared.types import AetherEvent, EventType


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        async def handler(event: AetherEvent):
            received.append(event)

        bus.subscribe(EventType.PING, handler)
        event = AetherEvent(type=EventType.PING, data={"test": True})
        await bus.publish(event)
        assert len(received) == 1
        assert received[0].data["test"] is True

    @pytest.mark.asyncio
    async def test_no_handler_no_error(self):
        bus = EventBus()
        event = AetherEvent(type=EventType.PONG)
        await bus.publish(event)  # Should not raise

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_crash_bus(self):
        bus = EventBus()

        async def bad_handler(event):
            raise ValueError("test error")

        bus.subscribe(EventType.PING, bad_handler)
        event = AetherEvent(type=EventType.PING)
        await bus.publish(event)  # Should not raise — error is logged

    @pytest.mark.asyncio
    async def test_backpressure_drops_events(self):
        """When inflight limit is exceeded, new events are dropped."""
        bus = EventBus()
        received = []
        proceed = asyncio.Event()

        async def slow_handler(event: AetherEvent):
            received.append(event)
            await proceed.wait()  # Block until we release

        bus.subscribe(EventType.PING, slow_handler)
        bus.set_max_inflight(EventType.PING, 2)

        # Start 2 events that will block (filling the limit)
        e1 = AetherEvent(type=EventType.PING, data={"n": 1})
        e2 = AetherEvent(type=EventType.PING, data={"n": 2})
        t1 = asyncio.create_task(bus.publish(e1))
        t2 = asyncio.create_task(bus.publish(e2))
        await asyncio.sleep(0.01)  # Let handlers start

        # This should be dropped (inflight is 2/2)
        e3 = AetherEvent(type=EventType.PING, data={"n": 3})
        await bus.publish(e3)

        assert bus.get_dropped_count(EventType.PING) == 1
        assert len(received) == 2  # Only first 2 received

        # Release the blocked handlers
        proceed.set()
        await t1
        await t2

    @pytest.mark.asyncio
    async def test_backpressure_no_limit_allows_all(self):
        """Without a limit set, all events are processed (backwards compatible)."""
        bus = EventBus()
        received = []

        async def handler(event: AetherEvent):
            received.append(event)

        bus.subscribe(EventType.PING, handler)
        # No set_max_inflight call — should allow everything
        for i in range(10):
            await bus.publish(AetherEvent(type=EventType.PING, data={"n": i}))

        assert len(received) == 10
        assert bus.get_dropped_count(EventType.PING) == 0


class TestConfig:
    def test_config_loads(self):
        from src.shared.config import get_settings

        settings = get_settings()
        assert settings.websocket_port == 8765
        assert settings.health_port == 8767

    def test_yaml_config_loads(self):
        from src.shared.config import get_yaml_config

        config = get_yaml_config()
        # v1.0 top-level keys per configs/default_config.yaml:
        # aether, onboarding, persona, llm, voice, ui, memory, avatar
        assert "aether" in config
        assert "llm" in config
        assert "memory" in config
