"""[SILENT] Protocol — Triple gate for determining if speech is directed at Aether.

Gate 1: Speaker verification (TitaNet) — non-owner voices auto-[SILENT]
Gate 2: Intent pre-filter (qwen3:8b) — quick classification: directed at Aether?
Gate 3: Main LLM context check — full [SILENT] protocol in system prompt

Manual toggle: "silent mode" / "people around" → minimal responses
               "we're alone" / "normal mode" → deactivate
"""

import re
import threading

from loguru import logger

from src.shared.config import get_yaml_config

# Manual toggle patterns
_SILENT_ACTIVATE = re.compile(
    r"(?:silent\s*mode|people\s*around|company\s*over|not\s*alone|mute\s*mode)",
    re.IGNORECASE,
)
_SILENT_DEACTIVATE = re.compile(
    r"(?:we'?re\s*alone|normal\s*mode|unmute|just\s*(?:us|me)|no\s*one\s*(?:around|here))",
    re.IGNORECASE,
)

# Signs NOT talking to Aether (for Gate 2 pre-filter)
_NOT_DIRECTED_PATTERNS = [
    re.compile(r"\b(?:hey|hi|yo)\s+\w{2,}", re.IGNORECASE),  # Greeting someone by name
    re.compile(r"\b(?:you\s+guys|y'?all|everyone|folks)\b", re.IGNORECASE),  # Plural address
    re.compile(r"\b(?:tell\s+(?:him|her|them))\b", re.IGNORECASE),  # Talking about third parties
]

# Signs IS talking to Aether (for Gate 2 pre-filter)
_DIRECTED_PATTERNS = [
    re.compile(r"\baether\b", re.IGNORECASE),  # Says her name
    re.compile(r"\b(?:what\s+time|weather|search|look\s+up|remind\s+me|set\s+a)\b", re.IGNORECASE),  # AI tasks
    re.compile(r"\b(?:play|open|close|screenshot|type)\b", re.IGNORECASE),  # Tool commands
]

# Gate 2 LLM classification prompt
_INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier. Determine if the following speech is directed at an AI assistant named Aether, or if it's someone talking to other people in the room.

Speech: "{text}"

Reply with exactly one word: DIRECTED or NOT_DIRECTED"""


class SilentGate:
    """Triple-gate system for the [SILENT] protocol."""

    def __init__(self) -> None:
        self._manual_silent: bool | None = None  # None = auto mode
        config = get_yaml_config()
        self._mode = config.get("persona", {}).get("silent_mode", "auto")

    @property
    def is_manual_silent(self) -> bool:
        """Check if manual silent mode is active."""
        return self._manual_silent is True

    def check_manual_toggle(self, text: str) -> str | None:
        """Check if text is a manual toggle command. Returns response or None."""
        if _SILENT_ACTIVATE.search(text):
            self._manual_silent = True
            logger.info("SilentGate: manual silent mode ACTIVATED")
            return "Got it. I'll keep quiet."

        if _SILENT_DEACTIVATE.search(text):
            self._manual_silent = False
            logger.info("SilentGate: manual silent mode DEACTIVATED")
            return "Back to normal."

        return None

    def gate1_speaker_verified(self, is_owner: bool) -> bool:
        """Gate 1: Speaker verification. Returns True if speech should proceed."""
        if not is_owner:
            logger.debug("SilentGate: Gate 1 BLOCKED — not the user's voice")
            return False
        return True

    def gate2_intent_prefilter(self, text: str) -> bool | None:
        """Gate 2: Fast local intent pre-filter.

        Returns True (directed), False (not directed), or None (ambiguous — pass to Gate 3).
        """
        # Manual override takes precedence
        if self._manual_silent is True:
            logger.debug("SilentGate: Gate 2 BLOCKED — manual silent mode")
            return False

        if self._manual_silent is False:
            return True  # Manual "we're alone" — skip filtering

        text_lower = text.lower().strip()

        # Check directed patterns first (higher priority)
        for pattern in _DIRECTED_PATTERNS:
            if pattern.search(text_lower):
                logger.debug("SilentGate: Gate 2 PASS — directed pattern match")
                return True

        # Check not-directed patterns
        for pattern in _NOT_DIRECTED_PATTERNS:
            if pattern.search(text_lower):
                logger.debug("SilentGate: Gate 2 BLOCKED — not-directed pattern match")
                return False

        # Ambiguous — let Gate 3 (main LLM) decide
        return None

    async def gate2_llm_classify(self, text: str) -> bool:
        """Gate 2 LLM fallback: Use qwen3:8b to classify intent when patterns are ambiguous."""
        try:
            import asyncio

            from src.brain.clients import call_ollama

            prompt = _INTENT_CLASSIFICATION_PROMPT.format(text=text[:200])
            result = await asyncio.wait_for(
                call_ollama(
                    system="You are a speech intent classifier. Reply with exactly one word.",
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=5.0,  # Don't block voice pipeline longer than 5s
            )
            is_directed = "directed" in result.lower() and "not_directed" not in result.lower()
            logger.debug(f"SilentGate: Gate 2 LLM classified as {'DIRECTED' if is_directed else 'NOT_DIRECTED'}")
            return is_directed
        except TimeoutError:
            logger.warning("SilentGate: Gate 2 LLM classification timed out (5s)")
            return True  # On timeout, default to responding
        except Exception as e:
            logger.warning(f"SilentGate: Gate 2 LLM classification failed: {e}")
            return True  # On error, default to responding (better to respond than miss)

    async def should_respond(self, text: str, is_owner: bool = True) -> bool:
        """Run the full triple gate. Returns True if Aether should respond."""
        # Gate 1: Speaker verification
        if not self.gate1_speaker_verified(is_owner):
            return False

        # Check manual toggle first
        toggle_response = self.check_manual_toggle(text)
        if toggle_response is not None:
            return True  # Always respond to toggle commands

        # Gate 2: Intent pre-filter (patterns first)
        gate2_result = self.gate2_intent_prefilter(text)
        if gate2_result is not None:
            return gate2_result

        # Gate 2 ambiguous → try LLM classification
        if self._mode == "auto":
            return await self.gate2_llm_classify(text)

        # Default: respond
        return True


# Module-level singleton (double-checked locking for thread safety)
_silent_gate: SilentGate | None = None
_silent_gate_lock = threading.Lock()


def get_silent_gate() -> SilentGate:
    """Get or create the SilentGate singleton."""
    global _silent_gate
    if _silent_gate is None:
        with _silent_gate_lock:
            if _silent_gate is None:
                _silent_gate = SilentGate()
    return _silent_gate
