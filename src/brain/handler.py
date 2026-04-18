"""Brain event handler — v1.0 streaming chat loop.

Receives USER_MESSAGE, builds the system prompt with active persona + memory context,
routes through the tier classifier, streams tokens via llm_router / fallback, and
publishes RESPONSE_TEXT_CHUNK events for the frontend to assemble.

No tool calling, no agent dispatch, no emotion tracking in v1.0 — all deferred to v2.
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from src.brain.fallback import call_with_fallback
from src.brain.llm_router import Tier, route_complexity_async
from src.brain.persona import build_system_prompt
from src.brain.response_formatter import format_for_mode
from src.brain.sanitizer import sanitize_response
from src.core.events import event_bus
from src.shared.types import AetherEvent, EventType, InteractionMode


# Max conversation turns to include in LLM context window.
CONTEXT_TURNS = 20


async def _get_recent_history(n: int) -> list[dict[str, str]]:
    """Pull the last n conversation turns from memory. Returns empty list on failure."""
    try:
        from src.memory.store import get_recent_turns

        return await get_recent_turns(n_turns=n)
    except Exception as e:
        logger.debug(f"brain: recent-history fetch failed (non-fatal): {e}")
        return []


async def _get_rag_context(query: str) -> list[dict[str, Any]]:
    """Search memory for context relevant to the current query. Returns empty on failure."""
    try:
        from src.memory.store import search_memory

        return await search_memory(query, n_results=5)
    except Exception as e:
        logger.debug(f"brain: memory search failed (non-fatal): {e}")
        return []


def _coerce_mode(raw: Any) -> InteractionMode:
    """Normalise a mode value from the event payload."""
    if isinstance(raw, InteractionMode):
        return raw
    if isinstance(raw, str):
        try:
            return InteractionMode(raw)
        except ValueError:
            logger.warning(f"brain: unknown interaction mode '{raw}' — defaulting to TEXT")
    return InteractionMode.TEXT


async def on_user_message(event: AetherEvent) -> None:
    """Handle a USER_MESSAGE event: route, stream, publish response chunks + final."""
    text: str = event.data.get("text", "").strip()
    if not text:
        return

    mode = _coerce_mode(event.data.get("mode"))
    started = time.time()
    logger.info(f"brain: processing ({len(text)} chars, mode={mode.value})")

    await event_bus.publish(
        AetherEvent(
            type=EventType.RESPONSE_START,
            data={"mode": mode.value},
            source_module="brain",
        )
    )

    tier: Tier = await route_complexity_async(text)
    logger.debug(f"brain: routed to tier {tier.value}")

    history = await _get_recent_history(CONTEXT_TURNS)
    rag = await _get_rag_context(text)
    system_prompt = build_system_prompt(mode=mode, rag_context=rag)

    messages: list[dict[str, str]] = []
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    assembled: list[str] = []
    try:
        async for chunk in call_with_fallback(messages=messages, tier=tier, system=system_prompt):
            if chunk.content:
                assembled.append(chunk.content)
                await event_bus.publish(
                    AetherEvent(
                        type=EventType.RESPONSE_TEXT_CHUNK,
                        data={"text": chunk.content, "mode": mode.value},
                        source_module="brain",
                    )
                )
    except Exception as e:
        logger.exception(f"brain: LLM call failed: {e}")
        error_text = "I'm having trouble reaching the language model right now. Check your LLM provider in Settings."
        await event_bus.publish(
            AetherEvent(
                type=EventType.RESPONSE_TEXT_READY,
                data={"text": error_text, "mode": mode.value, "is_error": True},
                source_module="brain",
            )
        )
        await event_bus.publish(
            AetherEvent(type=EventType.RESPONSE_END, data={"mode": mode.value}, source_module="brain")
        )
        return

    raw_response = "".join(assembled).strip()
    final_text = format_for_mode(sanitize_response(raw_response), mode)

    await event_bus.publish(
        AetherEvent(
            type=EventType.RESPONSE_TEXT_READY,
            data={"text": final_text, "mode": mode.value, "is_interim": False},
            source_module="brain",
        )
    )
    await event_bus.publish(
        AetherEvent(
            type=EventType.RESPONSE_END,
            data={"mode": mode.value, "tier": tier.value, "latency_ms": int((time.time() - started) * 1000)},
            source_module="brain",
        )
    )

    try:
        from src.memory.store import store_conversation_turn

        await store_conversation_turn(role="user", content=text)
        await store_conversation_turn(role="assistant", content=final_text)
    except Exception as e:
        logger.debug(f"brain: conversation-history persist failed (non-fatal): {e}")


def register_brain_handlers() -> None:
    """Wire up brain handlers to the EventBus."""
    event_bus.subscribe(EventType.USER_MESSAGE, on_user_message)
    logger.info("brain: handlers registered (USER_MESSAGE)")
