"""Context-aware backchannel manager — triggers based on content, not random probability.

Voice mode only. Content-triggered, not timer-based.
After emotional statements → "yeah", "I hear you"
After explanations → "mm-hmm", "right"
After questions → silence (thinking)
After frustration → "that sounds rough"
"""

import random
import re

from loguru import logger

from src.shared.config import get_yaml_config

# Content triggers and their backchannel pools
_EMOTIONAL_PATTERNS = [
    re.compile(r"\b(?:frustrated|annoyed|angry|pissed|furious|upset)\b", re.IGNORECASE),
    re.compile(r"\b(?:stressed|overwhelmed|exhausted|burned\s*out|tired\s+of)\b", re.IGNORECASE),
    re.compile(r"\b(?:sad|depressed|lonely|miss(?:ing)?|heartbroken)\b", re.IGNORECASE),
    re.compile(r"\b(?:worried|anxious|nervous|scared|afraid)\b", re.IGNORECASE),
]

_FRUSTRATION_PATTERNS = [
    re.compile(r"\b(?:broken|doesn't\s+work|won't\s+work|keeps?\s+(?:failing|crashing|breaking))\b", re.IGNORECASE),
    re.compile(r"\b(?:stupid|ridiculous|bullshit|crap|garbage|useless)\b", re.IGNORECASE),
    re.compile(r"\b(?:sick\s+(?:of|and\s+tired)|fed\s+up|had\s+enough|can't\s+deal)\b", re.IGNORECASE),
]

_EXPLANATION_PATTERNS = [
    re.compile(r"\b(?:because|since|so\s+basically|the\s+reason|what\s+happened\s+(?:was|is))\b", re.IGNORECASE),
    re.compile(r"\b(?:turns?\s+out|apparently|essentially|fundamentally)\b", re.IGNORECASE),
    re.compile(r"\b(?:I\s+(?:think|believe|figured|realized|noticed))\b", re.IGNORECASE),
]

_QUESTION_PATTERNS = [
    re.compile(r"\?\s*$"),
    re.compile(r"^(?:what|where|when|why|how|who|which|is|are|do|does|can|could|would|should)\b", re.IGNORECASE),
]

# Backchannel response pools
_BACKCHANNELS = {
    "emotional": ["yeah", "I hear you", "mm", "yeah, that's rough"],
    "frustration": ["that sounds rough", "yeah, that sucks", "ugh, yeah"],
    "explanation": ["mm-hmm", "right", "got it", "yeah"],
    "agreement": ["yeah", "totally", "right", "for sure"],
}


class BackchannelManager:
    """Determines when and what backchannel to inject during voice mode."""

    def __init__(self) -> None:
        config = get_yaml_config()
        self._enabled = config.get("persona", {}).get("backchannels_enabled", True)
        self._last_backchannel: str = ""

    @property
    def enabled(self) -> bool:
        """Whether backchannels are enabled."""
        return self._enabled

    def analyze(self, text: str) -> str | None:
        """Analyze speech and return a backchannel phrase, or None if silence is appropriate.

        Only for voice mode. Returns None for questions or when disabled.
        """
        if not self._enabled:
            return None

        text = text.strip()
        if not text:
            return None

        # Questions → silence (she's thinking)
        for pattern in _QUESTION_PATTERNS:
            if pattern.search(text):
                return None

        # Frustration → empathetic backchannel
        for pattern in _FRUSTRATION_PATTERNS:
            if pattern.search(text):
                return self._pick("frustration")

        # Emotional → validating backchannel
        for pattern in _EMOTIONAL_PATTERNS:
            if pattern.search(text):
                return self._pick("emotional")

        # Explanations → acknowledgment backchannel
        for pattern in _EXPLANATION_PATTERNS:
            if pattern.search(text):
                return self._pick("explanation")

        # Short statements (< 10 words) often don't need backchannels
        if len(text.split()) < 10:
            return None

        # Long statements → generic acknowledgment
        return self._pick("agreement")

    def _pick(self, category: str) -> str:
        """Pick a random backchannel, avoiding repeats."""
        pool = _BACKCHANNELS.get(category, _BACKCHANNELS["agreement"])
        # Filter out last used to avoid repetition
        available = [b for b in pool if b != self._last_backchannel]
        if not available:
            available = pool
        choice = random.choice(available)  # noqa: S311  # nosec B311
        self._last_backchannel = choice
        logger.debug(f"Backchannel: '{choice}' (category={category})")
        return choice


# Module singleton
_manager: BackchannelManager | None = None


def get_backchannel_manager() -> BackchannelManager:
    """Get or create the BackchannelManager singleton."""
    global _manager
    if _manager is None:
        _manager = BackchannelManager()
    return _manager
