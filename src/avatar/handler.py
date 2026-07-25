"""Avatar event handler — syncs speaking state with LivePortrait."""

import asyncio

from loguru import logger

from src.avatar.client import get_avatar_client
from src.core.events import event_bus
from src.shared.types import AetherEvent, EventType

# Track the auto-reset task so we can cancel if a new response arrives
_speaking_reset_task: asyncio.Task | None = None

# Lazy asyncio.Lock — must not be created at module scope (event loop mismatch)
_speaking_lock: asyncio.Lock | None = None


def _get_speaking_lock() -> asyncio.Lock:
    """Lazily create asyncio.Lock inside the running event loop."""
    global _speaking_lock
    if _speaking_lock is None:
        _speaking_lock = asyncio.Lock()
    return _speaking_lock


# Estimated speaking duration: ~150ms per word, capped at 30s
_MAX_SPEAKING_DURATION = 30.0
_MS_PER_WORD = 150


async def _reset_speaking_after(delay: float) -> None:
    """Reset speaking state after a delay."""
    try:
        await asyncio.sleep(delay)
        client = get_avatar_client()
        await client.set_speaking(False)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"Avatar: failed to reset speaking state: {e}")


async def on_response_ready(event: AetherEvent) -> None:
    """When Aether starts responding, tell avatar she's speaking."""
    global _speaking_reset_task

    is_interim = event.data.get("is_interim", False)
    if not is_interim:
        async with _get_speaking_lock():
            client = get_avatar_client()
            await client.set_speaking(True)
            # Cancel previous reset timer if any
            if _speaking_reset_task and not _speaking_reset_task.done():
                _speaking_reset_task.cancel()
            # Estimate speaking duration from response length
            text = event.data.get("text", "")
            word_count = len(text.split())
            duration = min(word_count * _MS_PER_WORD / 1000, _MAX_SPEAKING_DURATION)
            duration = max(duration, 2.0)  # At least 2 seconds
            _speaking_reset_task = asyncio.create_task(_reset_speaking_after(duration))


async def on_user_message(event: AetherEvent) -> None:
    """Reset speaking state when The user starts talking."""
    global _speaking_reset_task
    async with _get_speaking_lock():
        if _speaking_reset_task and not _speaking_reset_task.done():
            _speaking_reset_task.cancel()
        client = get_avatar_client()
        await client.set_speaking(False)


async def initialize_avatar() -> None:
    """Check LivePortrait availability and broadcast stream URL."""
    global _speaking_reset_task, _speaking_lock
    _speaking_reset_task = None  # Reset on init to avoid stale task from old event loop
    _speaking_lock = None  # Reset so fresh lock is created for current event loop

    from src.core.health import register_module, update_module_status

    register_module("avatar", "starting")
    client = get_avatar_client()
    available = await client.check_health()
    status = "ready" if available else "unavailable"
    update_module_status("avatar", status)

    if available:
        logger.info(f"Avatar: LivePortrait available at {client.stream_url}")
        # Broadcast avatar availability to connected desktop clients
        await event_bus.publish(
            AetherEvent(
                type=EventType.MODULE_READY,
                data={"module": "avatar", "stream_url": client.stream_url, "available": True},
                source_module="avatar",
            )
        )
    else:
        logger.warning("Avatar: LivePortrait not available — avatar disabled for this session")


def register_avatar_handlers() -> None:
    """Subscribe to events that control avatar behavior."""
    event_bus.subscribe(EventType.RESPONSE_TEXT_READY, on_response_ready)
    event_bus.subscribe(EventType.USER_MESSAGE, on_user_message)
    logger.info("Avatar: handlers registered")
