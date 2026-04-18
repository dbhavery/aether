"""System prompt builder — wraps the active persona pack's prompt with runtime context.

The active persona (loaded by src.personas.manager) provides the core personality
prompt. This module layers on mode-specific hints, current date/time, RAG context,
and a prompt-injection guard. No hardcoded personality — the persona pack is the
source of truth.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from src.brain.content_guard import get_injection_guard_system_prompt
from src.shared.types import InteractionMode


_MODE_HINTS: dict[InteractionMode, str] = {
    InteractionMode.TEXT: (
        "The user is typing. Text mode — full formatting allowed "
        "(markdown, lists, code blocks). Be as detailed as the question warrants."
    ),
    InteractionMode.VOICE: (
        "This is a live voice conversation. Respond naturally, briefly, "
        "conversationally. No markdown, no lists, no asterisks, no stage directions. "
        "Write as spoken words. Short sentences (around 30 words maximum). "
        "Natural transitions."
    ),
    InteractionMode.VIDEO: (
        "The user is in a video call with you. Be natural and conversational, "
        "like face-to-face. Keep responses brief and easy to speak. "
        "No markdown or formatting."
    ),
}


_FALLBACK_PROMPT = (
    "You are a helpful AI assistant. Be direct, truthful, and concise. "
    "Never fabricate facts. If you don't know something, say so plainly."
)


def _get_active_persona_prompt() -> str:
    """Fetch the active persona's system_prompt from the persona manager.

    Returns a fallback prompt if no active persona is set (e.g., during onboarding
    or when the persona module hasn't finished loading yet).
    """
    try:
        from src.personas import get_persona_manager

        manager = get_persona_manager()
        active_id = manager.active_persona_id
        if active_id is None:
            return _FALLBACK_PROMPT
        pack = manager.get(active_id)
        if pack is None:
            logger.warning(f"persona: active id '{active_id}' not found in loaded packs")
            return _FALLBACK_PROMPT
        prompt = pack.manifest.personality.system_prompt
        return prompt.strip() if prompt else _FALLBACK_PROMPT
    except Exception as e:
        logger.debug(f"persona: could not load active persona ({e}) — using fallback prompt")
        return _FALLBACK_PROMPT


def build_system_prompt(
    mode: InteractionMode,
    rag_context: list[dict] | None = None,
    datetime_now: datetime | None = None,
) -> str:
    """Compose the full system prompt for the current turn.

    Layers, in order:
      1. Active persona's system prompt (from the loaded pack).
      2. Mode hint (text / voice / video).
      3. Current date and time.
      4. RAG context from memory, if any.
      5. Prompt-injection guard instructions.
    """
    now = datetime_now or datetime.now()
    time_str = now.strftime("%A, %B %d, %Y at %I:%M %p %Z").strip()

    persona_prompt = _get_active_persona_prompt()
    mode_hint = _MODE_HINTS.get(mode, _MODE_HINTS[InteractionMode.TEXT])

    context_block = ""
    if rag_context:
        chunks = [f"- {c.get('content', '')}" for c in rag_context[:5] if c.get("content")]
        if chunks:
            context_block = "\n\nRELEVANT CONTEXT FROM MEMORY:\n" + "\n".join(chunks)

    injection_guard = get_injection_guard_system_prompt()

    return (
        f"{persona_prompt}\n\n"
        f"INTERACTION MODE: {mode_hint}\n\n"
        f"CURRENT DATE AND TIME: {time_str}"
        f"{context_block}"
        f"{injection_guard}"
    )
