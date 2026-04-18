"""Fallback cascade for LLM calls.

Per docs/LLM-PROVIDERS.md §5, every call has a chain:

    HEAVY  ->  MAIN  ->  FAST  ->  Aether Guest (if opted in)  ->  raise

If the primary tier fails, we try the next. Rate limits get a bounded
exponential-backoff retry first (they are often transient). Auth errors break
out immediately — no point retrying a bad key, and doing so would mask the real
problem from the user.

Fallback events are logged at INFO and also published to the EventBus (best
effort — we never let an event-bus hiccup break a response) so Sandbox -> Status
can show "N calls fell back to MAIN in the last hour".
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from loguru import logger

from src.brain.llm_client import (
    AuthError,
    Chunk,
    LLMError,
    RateLimitError,
    complete,
)
from src.brain.llm_router import Tier, resolve_provider

# Ordered cascade: each tier points to the next one to try on failure.
_NEXT_TIER: Final[dict[Tier, Tier | None]] = {
    Tier.HEAVY: Tier.MAIN,
    Tier.MAIN: Tier.FAST,
    Tier.FAST: None,  # Tail; AetherGuest is considered separately via config flag.
}

_GUEST_MODEL: Final[str] = "groq/llama-3.3-70b-versatile"

# Rate-limit retry policy — small and bounded so we never stall a conversation.
_MAX_RATELIMIT_RETRIES: Final[int] = 2
_RATELIMIT_BACKOFF_BASE_S: Final[float] = 0.5
_RATELIMIT_BACKOFF_CAP_S: Final[float] = 4.0

# Strong references to in-flight observability publish tasks. Without this,
# ``loop.create_task`` returns a task that the event loop only weak-refs, so it
# can be garbage-collected mid-flight and the publish silently drops.
_pending_publish_tasks: set[asyncio.Task[Any]] = set()


async def call_with_fallback(
    messages: list[dict[str, Any]],
    tier: Tier,
    **kwargs: Any,
) -> AsyncIterator[Chunk]:
    """Yield chunks from ``complete(tier)``, cascading on failure.

    Cascade:
        requested tier  ->  (HEAVY -> MAIN -> FAST)  ->  AetherGuest if enabled
                         ->  re-raise the last error.

    Retry policy:
        * AuthError     -> do NOT retry. Fall through to the next tier immediately;
                           the user needs to fix their key.
        * RateLimitError-> bounded exponential backoff up to 2 retries on the same
                           tier, then fall through.
        * ProviderError / TimeoutError -> fall through immediately.

    Once we've yielded a single content chunk, we DO NOT switch tiers — mid-stream
    failures re-raise so the caller can surface them. Switching mid-stream would
    produce Frankenstein responses.
    """
    tried: list[Tier] = []
    last_error: LLMError | None = None
    yielded_content = False  # Once we've emitted real text, switching tiers is forbidden.

    current: Tier | None = tier
    while current is not None:
        tried.append(current)
        provider = resolve_provider(current)

        try:
            async for chunk in _call_tier_with_ratelimit_retry(
                messages, current, provider, **kwargs
            ):
                if chunk.content:
                    yielded_content = True
                yield chunk
            # Stream completed cleanly.
            if current is not tier:
                _log_fallback_success(requested=tier, used=current, chain=tried)
            return

        except AuthError as exc:
            logger.warning(
                f"Fallback: {current} auth failure ({exc.provider}): {exc} — "
                "not retrying (user-fixable). Trying next tier."
            )
            last_error = exc
        except RateLimitError as exc:
            logger.warning(
                f"Fallback: {current} rate-limited ({exc.provider}) after retries — trying next tier."
            )
            last_error = exc
        except LLMError as exc:
            logger.warning(
                f"Fallback: {current} failed ({exc.__class__.__name__} from {exc.provider}): {exc} — "
                "trying next tier."
            )
            last_error = exc

        if yielded_content:
            # We already streamed partial output to the caller. Switching tiers now
            # would splice a second response onto the first. Re-raise so the caller
            # can flag the turn as partial and move on.
            logger.error(
                f"Fallback: {current} failed mid-stream after partial content — "
                "not cascading (would corrupt response)"
            )
            raise last_error

        current = _NEXT_TIER[current]

    # Fell through the full chain — try Aether Guest if the user opted in.
    if _guest_enabled() and not yielded_content:
        logger.info(f"Fallback: cascade exhausted after {[t.value for t in tried]}, trying AetherGuest")
        try:
            async for chunk in _call_guest(messages, **kwargs):
                if chunk.content:
                    yielded_content = True
                yield chunk
            _log_fallback_success(requested=tier, used=Tier.FAST, chain=tried, via_guest=True)
            return
        except LLMError as exc:
            logger.error(f"Fallback: AetherGuest failed too: {exc}")
            last_error = exc
            if yielded_content:
                raise

    # Everything failed. Surface the most recent error to the caller.
    _publish_cascade_failure(requested=tier, chain=tried, error=last_error)
    if last_error is not None:
        raise last_error
    raise LLMError(
        "All LLM tiers failed and no error was recorded (this should not happen)",
        provider="unknown",
    )


# ---------------------------------------------------------------------------
# Per-tier call with rate-limit retry
# ---------------------------------------------------------------------------


async def _call_tier_with_ratelimit_retry(
    messages: list[dict[str, Any]],
    tier: Tier,
    provider: str,
    **kwargs: Any,
) -> AsyncIterator[Chunk]:
    """Call one tier; on RateLimitError, retry up to ``_MAX_RATELIMIT_RETRIES``
    times with exponential backoff, honouring ``Retry-After`` if present.

    Auth / provider / timeout errors propagate immediately — no retry here.

    IMPORTANT: Retry is only safe BEFORE we've yielded any content. Once a
    chunk has gone out, we can't rewind, so mid-stream failures re-raise.
    """
    attempt = 0
    while True:
        started_streaming = False
        try:
            async for chunk in complete(messages=messages, tier=tier, **kwargs):
                started_streaming = True
                yield chunk
            return  # Clean finish.
        except RateLimitError as exc:
            if started_streaming or attempt >= _MAX_RATELIMIT_RETRIES:
                raise
            delay = _backoff_delay(attempt, exc.retry_after)
            logger.info(
                f"Fallback: {tier} ({provider}) rate-limited, retrying in {delay:.2f}s "
                f"(attempt {attempt + 1}/{_MAX_RATELIMIT_RETRIES})"
            )
            await asyncio.sleep(delay)
            attempt += 1


def _backoff_delay(attempt: int, retry_after: float | None) -> float:
    """Exponential backoff with jitter; honour ``Retry-After`` when the server sent one."""
    if retry_after is not None and retry_after > 0:
        return min(retry_after, _RATELIMIT_BACKOFF_CAP_S * 2)
    base = min(_RATELIMIT_BACKOFF_BASE_S * (2**attempt), _RATELIMIT_BACKOFF_CAP_S)
    # +/- 25% jitter to avoid thundering-herd retries.
    jitter = base * 0.25
    return base + random.uniform(-jitter, jitter)  # noqa: S311 — not crypto


# ---------------------------------------------------------------------------
# Aether Guest path
# ---------------------------------------------------------------------------


def _guest_enabled() -> bool:
    """True if the user has opted into the Aether Guest hosted proxy."""
    try:
        from src.brain.llm_router import _read_llm_config

        return bool(_read_llm_config().get("guest_fallback_enabled", False))
    except Exception as exc:
        logger.debug(f"Fallback: guest-flag lookup failed ({exc!r}) — assuming disabled")
        return False


async def _call_guest(
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> AsyncIterator[Chunk]:
    """Stream from the Aether Guest endpoint (Groq-backed, rate-limited).

    Implemented as a direct litellm call with the pinned guest model string. No
    keyring lookup: the Cloudflare Worker proxy handles auth on our side (see
    docs/LLM-PROVIDERS.md §11).
    """
    try:
        import litellm
    except ImportError as exc:
        raise LLMError(
            "litellm is not installed — cannot use AetherGuest",
            provider="aether_guest",
            model=_GUEST_MODEL,
        ) from exc

    call_kwargs: dict[str, Any] = {
        "model": _GUEST_MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        **kwargs,
    }

    try:
        response = await litellm.acompletion(**call_kwargs)
        last_finish: str | None = None
        last_usage: dict[str, int] | None = None
        async for event in response:
            usage_obj = getattr(event, "usage", None)
            if usage_obj is not None:
                from src.brain.llm_client import _normalise_usage

                last_usage = _normalise_usage(usage_obj)
            choices = getattr(event, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            delta = getattr(choice, "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            finish = getattr(choice, "finish_reason", None)
            if finish:
                last_finish = finish
            if content:
                yield Chunk(content=content, finish_reason=None, usage=None)
        yield Chunk(content="", finish_reason=last_finish or "stop", usage=last_usage)
    except LLMError:
        raise
    except BaseException as exc:
        from src.brain.llm_client import _map_litellm_error

        raise _map_litellm_error(exc, provider="aether_guest", model=_GUEST_MODEL) from exc


# ---------------------------------------------------------------------------
# Observability — event-bus publishing is best-effort
# ---------------------------------------------------------------------------


def _log_fallback_success(
    *,
    requested: Tier,
    used: Tier,
    chain: list[Tier],
    via_guest: bool = False,
) -> None:
    """Log + publish a FALLBACK_USED event for Sandbox -> Status to display."""
    chain_str = " -> ".join(t.value for t in chain)
    via = "AetherGuest" if via_guest else used.value
    logger.info(f"Fallback: recovered via {via} (requested={requested.value}, chain={chain_str})")
    _publish_event(
        "FALLBACK_USED",
        {
            "requested_tier": requested.value,
            "used_tier": used.value,
            "chain": [t.value for t in chain],
            "via_guest": via_guest,
        },
    )


def _publish_cascade_failure(
    *,
    requested: Tier,
    chain: list[Tier],
    error: LLMError | None,
) -> None:
    """Log + publish a FALLBACK_EXHAUSTED event when every tier in the chain failed."""
    chain_str = " -> ".join(t.value for t in chain)
    logger.error(
        f"Fallback: cascade exhausted for tier={requested.value}, chain={chain_str}, "
        f"error={error.__class__.__name__ if error else 'unknown'}: {error}"
    )
    _publish_event(
        "FALLBACK_EXHAUSTED",
        {
            "requested_tier": requested.value,
            "chain": [t.value for t in chain],
            "error_class": error.__class__.__name__ if error else "unknown",
            "error_message": str(error) if error else "",
            "provider": error.provider if error else "unknown",
        },
    )


def _publish_event(event_name: str, data: dict[str, Any]) -> None:
    """Best-effort publish to the EventBus. Silently drops if unavailable.

    We use a string name rather than a strongly-typed EventType because the
    EventType enum is owned by another agent right now (per spec constraints).
    Once the FALLBACK_USED / FALLBACK_EXHAUSTED enums land, swap the string for
    EventType.FALLBACK_USED etc.
    """
    try:
        from src.core.events import event_bus
        from src.shared.types import AetherEvent
    except ImportError:
        return

    try:
        event = AetherEvent(
            type=event_name,  # type: ignore[arg-type] — will be an EventType once the enum exists
            data=data,
            source_module="brain.fallback",
        )
        # Fire-and-forget; don't await the publish in case caller is already
        # inside an async generator where awaiting would hold back yields.
        # ``get_running_loop`` is the 3.10+ replacement for ``get_event_loop``.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (called from a sync context). Skip publishing;
            # observability isn't worth forcing a new loop here.
            return
        # Retain a reference to the task so it isn't garbage-collected mid-flight
        # (RUF006). We don't need to await or cancel it — fire-and-forget is the
        # whole point — but we do need to keep the task alive.
        task = loop.create_task(event_bus.publish(event))
        _pending_publish_tasks.add(task)
        task.add_done_callback(_pending_publish_tasks.discard)
    except Exception as exc:
        logger.debug(f"Fallback: event publish failed ({exc!r}) — observability only")
