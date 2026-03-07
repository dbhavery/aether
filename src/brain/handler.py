"""Brain event handler — listens for USER_MESSAGE, routes to LLM, publishes RESPONSE_TEXT_READY."""

import asyncio
import contextlib
import random
import re
import time

from loguru import logger

from src.brain.clients import (
    call_claude,
    call_claude_with_tools,
    call_gemini,
    call_gemini_with_tools,
    call_ollama,
)
from src.brain.content_guard import wrap_external_content
from src.brain.persona import build_system_prompt
from src.brain.response_formatter import format_for_mode
from src.brain.router import LLMTier, route_async
from src.brain.sanitizer import sanitize_response
from src.core.events import event_bus
from src.memory.store import get_recent_turns, search_memory
from src.shared.config import get_yaml_config
from src.shared.types import EventType, InteractionMode, AetherEvent
from src.tools.approval_gate import HIGH_IMPACT_ACTIONS, ActionRisk, request_approval
from src.tools.dispatcher import TOOL_DEFINITIONS, dispatch_tool

# Max conversation turns to include in LLM context
CONTEXT_TURNS = 20
# Max tool call rounds before forcing a final text response
MAX_TOOL_ROUNDS = 5


# Agent intent patterns — checked before LLM routing
_AGENT_PATTERNS = [
    (re.compile(r"^research\s+(.+)", re.IGNORECASE), "research"),
    (re.compile(r"^look\s+(?:up|into)\s+(.+)", re.IGNORECASE), "research"),
    (re.compile(r"^draft\s+(?:an?\s+)?email\s+(.+)", re.IGNORECASE), "draft_email"),
    (re.compile(r"^write\s+(?:an?\s+)?email\s+(.+)", re.IGNORECASE), "draft_email"),
    (re.compile(r"^draft\s+(?:a\s+)?message\s+(.+)", re.IGNORECASE), "draft_message"),
    (re.compile(r"^write\s+(?:a\s+)?message\s+(.+)", re.IGNORECASE), "draft_message"),
    (re.compile(r"^draft\s+(?:a\s+)?document\s+(.+)", re.IGNORECASE), "draft_document"),
    (re.compile(r"^write\s+(?:a\s+)?document\s+(.+)", re.IGNORECASE), "draft_document"),
]


def _detect_agent_intent(text: str) -> tuple[str, str] | None:
    """Check if user message matches an agent dispatch pattern. Returns (intent, payload) or None."""
    for pattern, intent in _AGENT_PATTERNS:
        match = pattern.match(text.strip())
        if match:
            return intent, match.group(1)
    return None


async def _get_rag_context(query: str) -> list[dict]:
    try:
        return await search_memory(query, n_results=5)
    except Exception as e:
        logger.warning(f"Brain: RAG context fetch failed (non-blocking): {e}")
        return []


async def _call_with_tools(messages: list[dict], system: str, heavy: bool = False) -> str:
    """Agentic tool loop using Claude. Loops up to MAX_TOOL_ROUNDS times."""
    working_messages = list(messages)

    for round_num in range(MAX_TOOL_ROUNDS):
        response = await call_claude_with_tools(
            messages=working_messages,
            system=system,
            tools=TOOL_DEFINITIONS,
            heavy=heavy,
        )

        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            return response.get("text", "")

        # Build assistant message with tool_use blocks
        assistant_content = []
        if response.get("text"):
            assistant_content.append({"type": "text", "text": response["text"]})
        for tc in tool_calls:
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                }
            )
        working_messages.append({"role": "assistant", "content": assistant_content})

        # Execute each tool and build tool_result messages
        tool_results = []
        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc.get("arguments", {})

            # Check approval gate for high-impact actions
            risk = HIGH_IMPACT_ACTIONS.get(tool_name, ActionRisk.SAFE)
            if risk != ActionRisk.SAFE:
                approved = await request_approval(
                    tool_name, f"Use tool '{tool_name}' with args: {tool_args}", tool_args
                )
                if not approved:
                    tool_result = f"Tool '{tool_name}' cancelled — the user did not approve."
                else:
                    tool_result = await dispatch_tool(tool_name, tool_args)
            else:
                tool_result = await dispatch_tool(tool_name, tool_args)

            # Coerce to string — dispatch_tool may return None if handler forgets return
            tool_result = str(tool_result) if tool_result is not None else ""
            # Wrap external content in trust boundary to prevent prompt injection
            tool_result = wrap_external_content(tool_result, source=tool_name)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": tool_result,
                }
            )
            logger.info(f"Brain: tool '{tool_name}' round {round_num + 1} -> {len(tool_result)} chars")

        working_messages.append({"role": "user", "content": tool_results})

    # Exceeded max rounds — ask for final answer
    working_messages.append({"role": "user", "content": "Please provide your final answer now."})
    final = await call_claude(system=system, messages=working_messages)
    return final or "I completed the requested actions."


async def _call_gemini_with_tools(messages: list[dict], system: str, model_key: str = "gemini_model") -> str:
    """Agentic tool loop using Gemini. Loops up to MAX_TOOL_ROUNDS times."""
    working_messages = list(messages)

    for round_num in range(MAX_TOOL_ROUNDS):
        response = await call_gemini_with_tools(
            messages=working_messages,
            system=system,
            tools=TOOL_DEFINITIONS,
            model_key=model_key,
        )

        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            return response.get("text", "")

        # Build assistant message with function call parts
        assistant_content = []
        if response.get("text"):
            assistant_content.append({"type": "text", "text": response["text"]})
        for tc in tool_calls:
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                }
            )
        working_messages.append({"role": "assistant", "content": assistant_content})

        # Execute each tool
        tool_results = []
        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc.get("arguments", {})

            risk = HIGH_IMPACT_ACTIONS.get(tool_name, ActionRisk.SAFE)
            if risk != ActionRisk.SAFE:
                approved = await request_approval(
                    tool_name, f"Use tool '{tool_name}' with args: {tool_args}", tool_args
                )
                if not approved:
                    tool_result = f"Tool '{tool_name}' cancelled — the user did not approve."
                else:
                    tool_result = await dispatch_tool(tool_name, tool_args)
            else:
                tool_result = await dispatch_tool(tool_name, tool_args)

            # Coerce to string — dispatch_tool may return None if handler forgets return
            tool_result = str(tool_result) if tool_result is not None else ""
            # Wrap external content in trust boundary to prevent prompt injection
            tool_result = wrap_external_content(tool_result, source=tool_name)

            tool_results.append(
                {
                    "type": "tool_result",
                    "name": tc["name"],
                    "content": tool_result,
                }
            )
            logger.info(f"Brain: Gemini tool '{tool_name}' round {round_num + 1} -> {len(tool_result)} chars")

        working_messages.append({"role": "user", "content": tool_results})

    # Exceeded max rounds
    working_messages.append({"role": "user", "content": "Please provide your final answer now."})
    result = await call_gemini(system=system, model_key=model_key, messages=working_messages)
    return result or "I completed the requested actions."


async def _call_with_fallback(tier: str, messages: list[dict], system: str) -> str:
    """Try the requested tier with multi-turn messages. Fall back gracefully if it fails."""
    try:
        if tier == LLMTier.FAST:
            return await call_ollama(system=system, messages=messages)
        elif tier == LLMTier.CLAUDE:
            return await call_claude(system=system, heavy=False, messages=messages)
        elif tier == LLMTier.CLAUDE_HEAVY:
            return await call_claude(system=system, heavy=True, messages=messages)
        elif tier == LLMTier.GEMINI:
            return await call_gemini(system=system, model_key="gemini_model", messages=messages)
        elif tier == LLMTier.GEMINI_FAST:
            return await call_gemini(system=system, model_key="gemini_fast_model", messages=messages)
        elif tier == LLMTier.GEMINI_PRO:
            return await call_gemini(system=system, model_key="gemini_pro_model", messages=messages)
        else:
            return await call_claude(system=system, heavy=False, messages=messages)
    except Exception as primary_err:
        logger.warning(f"Brain: primary tier {tier} failed ({primary_err}), trying fallback chain")
        # CLAUDE_HEAVY falls back to regular CLAUDE (sonnet), then GEMINI, then FAST
        if tier != LLMTier.CLAUDE:
            try:
                return await call_claude(system=system, heavy=False, messages=messages)
            except Exception as claude_err:
                logger.warning(f"Brain: CLAUDE fallback failed ({claude_err})")
        if tier not in (LLMTier.GEMINI, LLMTier.GEMINI_FAST, LLMTier.GEMINI_PRO):
            try:
                return await call_gemini(system=system, model_key="gemini_model", messages=messages)
            except Exception as gemini_err:
                logger.warning(f"Brain: GEMINI fallback failed ({gemini_err})")
        if tier != LLMTier.FAST:
            return await call_ollama(system=system, messages=messages)
        raise


async def on_user_message(event: AetherEvent) -> None:
    text = event.data.get("text", "")
    mode_str = event.data.get("mode", InteractionMode.TEXT)
    try:
        mode = InteractionMode(mode_str) if isinstance(mode_str, str) else mode_str
    except ValueError:
        logger.warning(f"Brain: invalid interaction mode '{mode_str}', defaulting to TEXT")
        mode = InteractionMode.TEXT

    if not text.strip():
        return

    start_time = time.time()
    logger.info(f"Brain: processing '{text[:60]}...' in {mode} mode")

    # Feed user message to emotion tracker for tone adaptation
    from src.persona.emotion_tracker import get_emotion_tracker

    get_emotion_tracker().analyze(text)

    # Voice mode: inject backchannel and filler phrases
    if mode in (InteractionMode.VOICE, InteractionMode.VIDEO):
        try:
            from src.persona.backchannels import get_backchannel_manager
            from src.persona.fillers import get_filler_generator

            backchannel = get_backchannel_manager().analyze(text)
            if backchannel:
                await event_bus.publish(
                    AetherEvent(
                        type=EventType.RESPONSE_TEXT_READY,
                        data={"text": backchannel, "emotion": "neutral", "is_interim": True, "mode": str(mode)},
                        source_module="brain",
                    )
                )

            filler = get_filler_generator().get_filler(text)
            if filler:
                await event_bus.publish(
                    AetherEvent(
                        type=EventType.RESPONSE_TEXT_READY,
                        data={"text": filler, "emotion": "neutral", "is_interim": True, "mode": str(mode)},
                        source_module="brain",
                    )
                )
        except Exception as e:
            logger.debug(f"Brain: backchannel/filler injection failed (non-critical): {e}")

    # Check for memory corrections first
    from src.persona.memory_corrections import detect_correction

    is_correction, correction_text = detect_correction(text)
    if is_correction:
        logger.info(f"Brain: detected memory correction — '{correction_text[:60]}'")
        await event_bus.publish(
            AetherEvent(
                type=EventType.MEMORY_CORRECTION,
                data={
                    "correction_text": correction_text,
                    "original_context": text,
                },
                source_module="brain",
            )
        )
        # Still respond to the user via LLM so Aether acknowledges naturally
        # (the LLM will generate an appropriate acknowledgment)

    # Check for agent dispatch patterns
    agent_match = _detect_agent_intent(text)
    if agent_match:
        intent, payload = agent_match
        logger.info(f"Brain: detected agent intent '{intent}' -- dispatching")
        try:
            from src.agents.dispatcher import dispatch

            result = await dispatch(intent, payload)
            result = sanitize_response(result)
            result = format_for_mode(result, mode)
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"Brain: agent response ready in {elapsed_ms:.0f}ms")
            await event_bus.publish(
                AetherEvent(
                    type=EventType.RESPONSE_TEXT_READY,
                    data={"text": result, "emotion": "neutral", "is_interim": False, "mode": str(mode)},
                    source_module="brain",
                )
            )
            await event_bus.publish(
                AetherEvent(
                    type=EventType.AGENT_TASK_COMPLETE,
                    data={"intent": intent, "payload": payload},
                    source_module="brain",
                )
            )
        except Exception as e:
            logger.error(f"Brain: agent dispatch failed: {e}")
            await event_bus.publish(
                AetherEvent(
                    type=EventType.RESPONSE_TEXT_READY,
                    data={"text": "I ran into an issue with that. Let me try a different approach.", "emotion": "apologetic", "mode": "text"},
                    source_module="brain",
                )
            )
        return

    # Notify if this will take a while (publish slow indicator after threshold)
    slow_sent = False
    slow_threshold_ms = get_yaml_config().get("persona", {}).get("slow_response_threshold_ms", 5000)
    slow_threshold_s = slow_threshold_ms / 1000

    async def slow_notify():
        nonlocal slow_sent
        await asyncio.sleep(slow_threshold_s)
        elapsed = time.time() - start_time
        if elapsed >= slow_threshold_s:
            slow_phrases = [
                "Hold on while I check that.",
                "Give me a moment.",
                "Let me look into that.",
                "One sec, on it.",
                "Just a moment.",
            ]
            slow_sent = True
            await event_bus.publish(
                AetherEvent(
                    type=EventType.RESPONSE_TEXT_READY,
                    data={
                        "text": random.choice(slow_phrases),  # noqa: S311  # nosec B311
                        "emotion": "thinking",
                        "is_interim": True,
                        "mode": str(mode),
                    },  # nosec B311
                    source_module="brain",
                )
            )

    slow_task = asyncio.create_task(slow_notify())

    try:
        # Get RAG context, conversation history, and route in parallel
        rag_context, history, tier = await asyncio.gather(
            _get_rag_context(text),
            get_recent_turns(limit=CONTEXT_TURNS),
            route_async(text),
        )

        # RAG context from memory is Aether's own conversation history — not external content.
        # Do NOT wrap in injection guard (that's for untrusted external sources).
        guarded_rag = rag_context if rag_context else []

        system_prompt = build_system_prompt(mode=mode, rag_context=guarded_rag)

        # Build multi-turn messages from history + current message
        messages = []
        for turn in history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": text})

        # Use tool calling loop for Claude and Gemini tiers, plain text for others
        if tier in (LLMTier.CLAUDE, LLMTier.CLAUDE_HEAVY):
            try:
                response_text = await _call_with_tools(messages, system_prompt, heavy=(tier == LLMTier.CLAUDE_HEAVY))
            except Exception as e:
                logger.warning(f"Brain: Claude tool calling failed ({e}), falling back to text-only")
                response_text = await _call_with_fallback(tier, messages, system_prompt)
        elif tier in (LLMTier.GEMINI, LLMTier.GEMINI_PRO):
            model_key = "gemini_pro_model" if tier == LLMTier.GEMINI_PRO else "gemini_model"
            try:
                response_text = await _call_gemini_with_tools(messages, system_prompt, model_key=model_key)
            except Exception as e:
                logger.warning(f"Brain: Gemini tool calling failed ({e}), falling back to text-only")
                response_text = await _call_with_fallback(tier, messages, system_prompt)
        else:
            response_text = await _call_with_fallback(tier, messages, system_prompt)

        slow_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await slow_task

        # Sanitize response — strip banned phrases before sending to user
        response_text = sanitize_response(response_text)

        # Format for interaction mode (voice = no markdown, text = full formatting)
        response_text = format_for_mode(response_text, mode)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Brain: response ready in {elapsed_ms:.0f}ms via {tier} ({len(response_text)} chars)")

        # Record metrics
        from src.core.metrics import get_metrics

        metrics = get_metrics()
        metrics.record_turn()
        metrics.record_response_latency(elapsed_ms)

        # Note: conversation storage is handled by memory/handler.py via EventBus
        # subscriptions to USER_MESSAGE and RESPONSE_TEXT_READY. Do NOT store here
        # to avoid duplicate writes to ChromaDB. (Wave 2 fix: C2 + C3)

        await event_bus.publish(
            AetherEvent(
                type=EventType.RESPONSE_TEXT_READY,
                data={"text": response_text, "emotion": "neutral", "is_interim": False, "mode": str(mode)},
                source_module="brain",
            )
        )

    except RuntimeError as e:
        slow_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await slow_task
        if "timed out" in str(e):
            logger.warning(f"Brain: LLM timed out for: {text[:50]}")
            await event_bus.publish(
                AetherEvent(
                    type=EventType.RESPONSE_TEXT_READY,
                    data={
                        "text": "I'm taking longer than usual to think. Give me a moment and try again.",
                        "emotion": "apologetic",
                        "mode": "text",
                    },
                    source_module="brain",
                )
            )
        else:
            logger.error(f"Brain: runtime error processing message: {e}")
            await event_bus.publish(
                AetherEvent(
                    type=EventType.RESPONSE_TEXT_READY,
                    data={
                        "text": "Something went wrong on my end. Give me a moment.",
                        "emotion": "apologetic",
                        "mode": "text",
                    },
                    source_module="brain",
                )
            )
    except Exception as e:
        slow_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await slow_task
        logger.error(f"Brain: fatal error processing message: {e}")
        await event_bus.publish(
            AetherEvent(
                type=EventType.RESPONSE_TEXT_READY,
                data={
                    "text": "Something went wrong on my end. Give me a moment.",
                    "emotion": "apologetic",
                    "mode": "text",
                },
                source_module="brain",
            )
        )


def register_brain_handlers() -> None:
    event_bus.subscribe(EventType.USER_MESSAGE, on_user_message)
    logger.info("Brain: handlers registered")
