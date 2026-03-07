"""Context-aware silence detection — extends VAD silence thresholds intelligently.

When the speaker ends on a continuation word ("and", "but", "so", etc.) or
appears to be mid-sentence, extends the silence threshold before VAD fires
on_speech_end. This prevents premature cutoffs during natural pauses.

Integrates with VADStream by wrapping the max_silence_ms dynamically.
"""

from loguru import logger

# Words that indicate the speaker intends to continue (English)
CONTINUATION_WORDS: frozenset[str] = frozenset(
    {
        "and",
        "but",
        "so",
        "because",
        "then",
        "or",
        "also",
        "plus",
        "like",
        "actually",
        "basically",
        "however",
        "although",
        "though",
        "since",
        "while",
        "whereas",
        "therefore",
        "moreover",
        "furthermore",
        "um",
        "uh",
        "well",
        # Spanish continuation words
        "y",
        "pero",
        "entonces",
        "porque",
        "o",
        "también",
        "además",
        "aunque",
        "pues",
    }
)

# Sentence-ending punctuation that indicates a complete thought
_SENTENCE_ENDINGS = frozenset({".", "?", "!", "...", "…"})


class ContextAwareSilenceDetector:
    """Dynamically adjusts silence threshold based on speech context.

    Usage:
        detector = ContextAwareSilenceDetector(base_silence_ms=800)
        effective_ms = detector.get_effective_silence_ms(partial_transcript)

    The detector does NOT replace VAD — it provides an adjusted silence duration
    that VADStream can use instead of its fixed max_silence_ms.
    """

    # Multipliers for silence threshold extension
    CONTINUATION_MULTIPLIER: float = 1.5  # Last word is a continuation word
    MID_SENTENCE_MULTIPLIER: float = 1.2  # No sentence-ending punctuation

    def __init__(self, base_silence_ms: float = 800.0):
        self._base_silence_ms = base_silence_ms

    @property
    def base_silence_ms(self) -> float:
        return self._base_silence_ms

    @base_silence_ms.setter
    def base_silence_ms(self, value: float) -> None:
        self._base_silence_ms = max(200.0, value)  # Floor at 200ms

    def get_effective_silence_ms(self, partial_transcript: str | None = None) -> float:
        """Return adjusted silence threshold based on transcript context.

        Args:
            partial_transcript: The text transcribed so far in the current
                speech segment. If None or empty, returns the base threshold.

        Returns:
            Adjusted silence duration in milliseconds.
        """
        if not partial_transcript or not partial_transcript.strip():
            return self._base_silence_ms

        text = partial_transcript.strip()
        last_word = text.split()[-1].lower().rstrip(".,!?;:")

        # Check for continuation word at end → extend by 1.5x
        if last_word in CONTINUATION_WORDS:
            effective = self._base_silence_ms * self.CONTINUATION_MULTIPLIER
            logger.debug(f"SilenceDetector: continuation word '{last_word}' — extending silence to {effective:.0f}ms")
            return effective

        # Check for mid-sentence (no sentence-ending punctuation) → extend by 1.2x
        last_char = text[-1]
        if last_char not in _SENTENCE_ENDINGS:
            effective = self._base_silence_ms * self.MID_SENTENCE_MULTIPLIER
            logger.debug(f"SilenceDetector: mid-sentence pause — extending silence to {effective:.0f}ms")
            return effective

        # Complete sentence detected — use base threshold
        return self._base_silence_ms

    def analyze_context(self, partial_transcript: str | None = None) -> dict:
        """Return analysis details (for debugging/logging).

        Returns:
            Dict with 'effective_ms', 'reason', 'last_word', 'multiplier'.
        """
        if not partial_transcript or not partial_transcript.strip():
            return {
                "effective_ms": self._base_silence_ms,
                "reason": "no_transcript",
                "last_word": None,
                "multiplier": 1.0,
            }

        text = partial_transcript.strip()
        last_word = text.split()[-1].lower().rstrip(".,!?;:")

        if last_word in CONTINUATION_WORDS:
            return {
                "effective_ms": self._base_silence_ms * self.CONTINUATION_MULTIPLIER,
                "reason": "continuation_word",
                "last_word": last_word,
                "multiplier": self.CONTINUATION_MULTIPLIER,
            }

        last_char = text[-1]
        if last_char not in _SENTENCE_ENDINGS:
            return {
                "effective_ms": self._base_silence_ms * self.MID_SENTENCE_MULTIPLIER,
                "reason": "mid_sentence",
                "last_word": last_word,
                "multiplier": self.MID_SENTENCE_MULTIPLIER,
            }

        return {
            "effective_ms": self._base_silence_ms,
            "reason": "complete_sentence",
            "last_word": last_word,
            "multiplier": 1.0,
        }
