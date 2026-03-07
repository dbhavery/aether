"""Complexity-aware filler generator — contextual thinking sounds for voice mode.

Simple questions: no filler, respond immediately.
Complex questions: filler after 2s — "let me think about that"
Research/tool tasks: immediate "on it", "let me check"
No repeat of same filler within 5 minutes.
"""

import re
import time

from loguru import logger

from src.shared.config import get_yaml_config

# Complexity classification patterns
_SIMPLE_PATTERNS = [
    re.compile(r"^(?:hi|hey|hello|good\s+(?:morning|afternoon|evening|night))\b", re.IGNORECASE),
    re.compile(r"^(?:yes|no|yeah|nah|nope|yep|sure|okay|ok|thanks|thank\s+you)\b", re.IGNORECASE),
    re.compile(r"^(?:what\s+time|what's\s+the\s+(?:time|date|weather))\b", re.IGNORECASE),
    re.compile(r"^(?:how\s+are\s+you|what's\s+up|sup)\b", re.IGNORECASE),
]

_RESEARCH_PATTERNS = [
    re.compile(r"\b(?:look\s+up|search|find|research|check|google|what\s+is|who\s+is)\b", re.IGNORECASE),
    re.compile(r"\b(?:open|play|run|start|launch|execute)\b", re.IGNORECASE),
    re.compile(r"\b(?:set\s+(?:a\s+)?(?:timer|alarm|reminder))\b", re.IGNORECASE),
    re.compile(r"\b(?:read\s+(?:the\s+)?file|list\s+(?:the\s+)?(?:files|directory))\b", re.IGNORECASE),
]

_COMPLEX_PATTERNS = [
    re.compile(r"\b(?:explain|analyze|compare|difference|how\s+does|why\s+does|what\s+would)\b", re.IGNORECASE),
    re.compile(r"\b(?:think\s+about|consider|evaluate|pros?\s+and\s+cons?|tradeoffs?)\b", re.IGNORECASE),
    re.compile(r"\b(?:write\s+(?:a|an|the)|draft|compose|create\s+a)\b", re.IGNORECASE),
    re.compile(r"\b(?:summarize|recap|overview|breakdown|deep\s+dive)\b", re.IGNORECASE),
]

# Filler phrase pools
_FILLER_PHRASES = {
    "thinking": [
        "let me think about that",
        "hmm, good question",
        "give me a second",
        "that's interesting, let me think",
        "hmm, let me consider that",
    ],
    "research": [
        "on it",
        "let me check",
        "one sec",
        "checking that now",
        "hold on, looking into it",
    ],
}

# Cooldown: don't repeat same filler within 5 minutes
_FILLER_COOLDOWN_SECONDS = 300


class FillerGenerator:
    """Generates contextual filler phrases for voice mode."""

    def __init__(self) -> None:
        config = get_yaml_config()
        self._enabled = config.get("persona", {}).get("fillers_enabled", True)
        self._recent_fillers: dict[str, float] = {}  # phrase → timestamp

    def classify_complexity(self, text: str) -> str:
        """Classify message complexity: 'simple', 'research', or 'complex'."""
        for pattern in _SIMPLE_PATTERNS:
            if pattern.search(text.strip()):
                return "simple"

        for pattern in _RESEARCH_PATTERNS:
            if pattern.search(text):
                return "research"

        for pattern in _COMPLEX_PATTERNS:
            if pattern.search(text):
                return "complex"

        # Default: check word count — long messages tend to be complex
        word_count = len(text.split())
        if word_count > 20:
            return "complex"

        return "simple"

    def get_filler(self, text: str) -> str | None:
        """Get a filler phrase based on message complexity.

        Returns None for simple questions (no filler needed).
        Returns a phrase for complex/research queries.
        """
        if not self._enabled:
            return None

        complexity = self.classify_complexity(text)

        if complexity == "simple":
            return None

        if complexity == "research":
            return self._pick("research")

        # Complex
        return self._pick("thinking")

    def _pick(self, category: str) -> str:
        """Pick a filler phrase, respecting cooldown."""
        now = time.time()
        pool = _FILLER_PHRASES.get(category, _FILLER_PHRASES["thinking"])

        # Filter out recently used
        available = [phrase for phrase in pool if now - self._recent_fillers.get(phrase, 0) > _FILLER_COOLDOWN_SECONDS]

        if not available:
            # All on cooldown — clear oldest and pick from full pool
            self._recent_fillers.clear()
            available = pool

        import random

        choice = random.choice(available)  # noqa: S311  # nosec B311
        self._recent_fillers[choice] = now
        logger.debug(f"Filler: '{choice}' (category={category})")
        return choice


# Module singleton
_generator: FillerGenerator | None = None


def get_filler_generator() -> FillerGenerator:
    """Get or create the FillerGenerator singleton."""
    global _generator
    if _generator is None:
        _generator = FillerGenerator()
    return _generator
