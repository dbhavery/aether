"""Brain event handler — v1.0 streaming chat loop.

Receives USER_MESSAGE, builds the system prompt with active persona + memory context,
routes through the tier classifier, streams tokens via llm_router / fallback, and
publishes RESPONSE_TEXT_CHUNK events for the frontend to assemble.

No tool calling, no agent dispatch, no emotion tracking in v1.0 — all deferred to v2.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from src.brain.cost import track_from_usage_dict
from src.brain.fallback import call_with_fallback
from src.brain.llm_router import Tier, route_complexity_async
from src.brain.persona import build_system_prompt
from src.brain.response_formatter import format_for_mode
from src.brain.sanitizer import sanitize_response
from src.core import trace
from src.core.events import event_bus
from src.core.metrics import get_metrics
from src.shared.types import AetherEvent, EventType, InteractionMode

# Max conversation turns to include in LLM context window.
CONTEXT_TURNS = 20


async def _get_recent_history(n: int) -> list[dict[str, str]]:
    """Pull the last n conversation turns from memory. Returns empty list on failure."""
    try:
        from src.memory.store import get_recent_turns

        return await get_recent_turns(n_turns=n)
    except Exception as e:
        # Degraded, not fatal: the turn proceeds without prior context. Logged
        # at WARNING so it is visible at the shipped INFO level rather than
        # silently producing an assistant with no memory of the conversation.
        logger.warning(f"brain: recent-history fetch failed, continuing without history: {e!r}")
        return []


async def _get_rag_context(query: str) -> list[dict[str, Any]]:
    """Search memory for context relevant to the current query. Returns empty on failure."""
    try:
        from src.memory.store import search_memory

        return await search_memory(query, n_results=5)
    except Exception as e:
        # Same reasoning as _get_recent_history: degraded, and visible at INFO.
        logger.warning(f"brain: memory search failed, continuing without RAG context: {e!r}")
        return []


async def _meter_turn(
    *,
    tier: Tier,
    provider: str | None,
    model: str | None,
    usage: dict[str, int] | None,
    latency_ms: float,
) -> None:
    """Record what the turn cost and how long it took.

    Both instruments existed and neither was ever called from production:
    ``src.brain.cost.track_usage`` had zero call sites, and the
    ``src.core.metrics`` recorders were only reached from the test suite, which
    is why /health served a permanently zeroed metrics block.

    Token counts were already being parsed off every provider response in
    ``src.brain.llm_client._normalise_usage`` and then discarded here, because
    this loop only ever read ``chunk.content``.

    Metering must never break a turn that already succeeded, so failures are
    logged at ERROR and swallowed deliberately rather than raised.
    """
    metrics = get_metrics()
    try:
        metrics.record_turn()
        metrics.record_response_latency(round(latency_ms, 1))
    except Exception:
        logger.exception("brain: failed to record turn metrics")

    if usage is None:
        # Not every provider reports usage on a stream, and Ollama only does so
        # when it feels like it. No record beats a guessed one.
        logger.debug(f"brain: no usage reported for tier {tier.value}; nothing to meter")
        trace.set_meta(usage_reported=False)
        return

    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or 0) or (prompt_tokens + completion_tokens)

    try:
        metrics.record_tokens(tier.value, total_tokens)
    except Exception:
        logger.exception("brain: failed to record token metrics")

    trace.set_meta(
        usage_reported=True,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        provider=provider,
        model=model,
        tier=tier.value,
    )

    if provider is None or model is None:
        logger.warning(
            "brain: usage reported without a provider/model identity; "
            "skipping cost record rather than attributing it to a guess"
        )
        return

    try:
        await track_from_usage_dict(provider=provider, model=model, usage=usage)
    except Exception:
        logger.exception("brain: failed to record token usage and cost")


async def _persist_turn(
    store_fn: Callable[..., Awaitable[str]],
    role: str,
    content: str,
    timestamp: float,
) -> None:
    """Write one conversation turn to memory, loudly on failure.

    The response has already been delivered by the time this runs, so a write
    failure must not abort the turn. It must not be hidden either: the previous
    version of this code caught everything and logged at DEBUG while the app
    ships at INFO, which hid a TypeError on every single turn for the life of
    the module. ERROR with a traceback is the floor for anything caught here.
    """
    try:
        await store_fn(role=role, content=content, timestamp=timestamp)
    except Exception:
        logger.exception(
            f"brain: failed to persist {role} turn to conversation history "
            f"(response already delivered; history will be missing this turn)"
        )


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
    """Handle a USER_MESSAGE event: route, stream, publish response chunks + final.

    Owns the turn trace for text mode. A voice turn is already open (started by
    ``src.voice.pipeline`` at push-to-talk release) and reaches this handler
    through the trace ContextVar, so whoever opened the trace closes it.
    """
    text: str = event.data.get("text", "").strip()
    if not text:
        return

    mode = _coerce_mode(event.data.get("mode"))
    owns_trace = trace.current_turn() is None
    if owns_trace:
        # A text submit is the moment the user starts waiting.
        trace.start_turn("text", prompt_chars=len(text))
    trace.set_meta(mode=mode.value)

    try:
        await _run_turn(text, mode)
    finally:
        # Closes on every exit path, including the LLM-failure return, so a
        # failed turn is still measured instead of vanishing from the log.
        if owns_trace:
            await trace.finish_turn()


async def _run_turn(text: str, mode: InteractionMode) -> None:
    """Route, stream, publish, meter, and persist one turn."""
    started = time.time()
    logger.info(f"brain: processing ({len(text)} chars, mode={mode.value})")

    await event_bus.publish(
        AetherEvent(
            type=EventType.RESPONSE_START,
            data={"mode": mode.value},
            source_module="brain",
        )
    )

    # Tier routing can itself cost an LLM call: route_complexity_async falls
    # through to a FAST-tier classification when neither keyword level fires,
    # and on a cold Ollama that dominates the turn. It gets its own stage so it
    # cannot hide inside an unaccounted gap.
    with trace.stage("tier_routing"):
        tier: Tier = await route_complexity_async(text)
    logger.debug(f"brain: routed to tier {tier.value}")

    with trace.stage("context_build"):
        history = await _get_recent_history(CONTEXT_TURNS)
        rag = await _get_rag_context(text)
        system_prompt = build_system_prompt(mode=mode, rag_context=rag)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    assembled: list[str] = []
    # Token usage and the provider/model that actually served the turn come off
    # the terminal chunk. The fallback cascade can land on a different tier than
    # the one we requested, so we take the identity the client reports rather
    # than re-resolving the requested tier, which would mis-attribute the cost.
    final_usage: dict[str, int] | None = None
    used_provider: str | None = None
    used_model: str | None = None
    try:
        # Records even when the stream raises: the context manager closes in a
        # finally, so a failed turn still reports how long it spent trying.
        with trace.stage("llm_complete"):
            async for chunk in call_with_fallback(messages=messages, tier=tier):
                if chunk.provider is not None:
                    used_provider = chunk.provider
                if chunk.model is not None:
                    used_model = chunk.model
                if chunk.usage is not None:
                    final_usage = chunk.usage
                if chunk.content:
                    if not assembled:
                        trace.mark("llm_first_token")
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
        # Mark the trace as a failed turn. Without this the recorded latency
        # looks like a normal measurement: the error sentence still goes to TTS,
        # so the turn produces stt, llm and tts timings and a first_audio mark
        # exactly as a working turn does. A failed turn's numbers must never be
        # quoted as response latency.
        trace.set_meta(turn_ok=False, error=f"{type(e).__name__}: {e}")
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

    trace.set_meta(turn_ok=True)
    with trace.stage("response_format"):
        raw_response = "".join(assembled).strip()
        final_text = format_for_mode(sanitize_response(raw_response), mode)

    # In voice and video modes this publish is where TTS runs: EventBus awaits
    # its handlers, so the tts_synth and playback stages are recorded inside it.
    await event_bus.publish(
        AetherEvent(
            type=EventType.RESPONSE_TEXT_READY,
            data={"text": final_text, "mode": mode.value, "is_interim": False},
            source_module="brain",
        )
    )
    latency_ms = (time.time() - started) * 1000.0
    await event_bus.publish(
        AetherEvent(
            type=EventType.RESPONSE_END,
            data={"mode": mode.value, "tier": tier.value, "latency_ms": int(latency_ms)},
            source_module="brain",
        )
    )

    with trace.stage("meter"):
        await _meter_turn(
            tier=tier,
            provider=used_provider,
            model=used_model,
            usage=final_usage,
            latency_ms=latency_ms,
        )

    # store_conversation_turn takes a required positional ``timestamp`` (see
    # src/memory/store.py); it feeds the document ID hash, so it cannot be
    # defaulted inside the store without changing IDs for existing rows. The
    # user turn is stamped when the message arrived, the assistant turn when
    # the reply finished, so history sorts in the order it happened.
    with trace.stage("memory_persist"):
        try:
            from src.memory.store import store_conversation_turn
        except ImportError:
            logger.exception("brain: memory store unavailable, conversation history not persisted")
        else:
            await _persist_turn(store_conversation_turn, "user", text, started)
            await _persist_turn(store_conversation_turn, "assistant", final_text, time.time())


def register_brain_handlers() -> None:
    """Wire up brain handlers to the EventBus."""
    event_bus.subscribe(EventType.USER_MESSAGE, on_user_message)
    logger.info("brain: handlers registered (USER_MESSAGE)")
