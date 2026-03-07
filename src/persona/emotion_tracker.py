"""Emotion tracker — detects the user's emotional state for tone adjustment.

8 emotion states, energy level 0-100, rolling window of last 10 messages.
Tone adjustment ONLY — Aether NEVER explicitly says "you seem stressed."
She just naturally adapts like a perceptive friend.
"""

import re
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from loguru import logger

from src.shared.config import get_yaml_config


class EmotionState(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    CURIOUS = "curious"
    FRUSTRATED = "frustrated"
    SAD = "sad"
    EXCITED = "excited"
    TIRED = "tired"
    ANXIOUS = "anxious"


# Keyword → emotion mapping (weighted by specificity)
_EMOTION_KEYWORDS: dict[EmotionState, list[re.Pattern]] = {
    EmotionState.HAPPY: [
        re.compile(r"\b(?:happy|great|awesome|amazing|perfect|wonderful|love|excited|stoked)\b", re.IGNORECASE),
        re.compile(r"\b(?:hell\s+yeah|let's\s+go|nice|sick|dope|fire)\b", re.IGNORECASE),
        re.compile(r"(?:!{2,}|😊|🎉|💪)", re.IGNORECASE),
    ],
    EmotionState.FRUSTRATED: [
        re.compile(r"\b(?:frustrated|annoyed|pissed|angry|furious|wtf|ugh)\b", re.IGNORECASE),
        re.compile(r"\b(?:broken|doesn't\s+work|won't\s+work|stupid|ridiculous|bullshit)\b", re.IGNORECASE),
        re.compile(r"\b(?:keeps?\s+(?:failing|crashing|breaking)|fed\s+up|sick\s+of)\b", re.IGNORECASE),
    ],
    EmotionState.SAD: [
        re.compile(r"\b(?:sad|depressed|lonely|miss(?:ing)?|lost|heartbroken|mourning)\b", re.IGNORECASE),
        re.compile(r"\b(?:sucks|terrible|awful|worst|horrible|devastated)\b", re.IGNORECASE),
    ],
    EmotionState.ANXIOUS: [
        re.compile(r"\b(?:worried|anxious|nervous|scared|afraid|stress(?:ed)?|overwhelmed)\b", re.IGNORECASE),
        re.compile(r"\b(?:panic|dread|what\s+if|can't\s+(?:sleep|stop\s+thinking))\b", re.IGNORECASE),
    ],
    EmotionState.TIRED: [
        re.compile(r"\b(?:tired|exhausted|burned?\s*out|drained|wiped|sleepy|can't\s+focus)\b", re.IGNORECASE),
        re.compile(r"\b(?:long\s+day|need\s+(?:a\s+)?break|running\s+on\s+empty)\b", re.IGNORECASE),
    ],
    EmotionState.EXCITED: [
        re.compile(r"\b(?:excited|pumped|hyped|can't\s+wait|finally|breakthrough)\b", re.IGNORECASE),
        re.compile(r"\b(?:figured\s+(?:it\s+)?out|it\s+works|nailed\s+it|crushed\s+it)\b", re.IGNORECASE),
    ],
    EmotionState.CURIOUS: [
        re.compile(r"\b(?:wonder(?:ing)?|curious|interesting|fascinating|hmm|huh)\b", re.IGNORECASE),
        re.compile(r"\b(?:how\s+does|why\s+does|what\s+if|explain|tell\s+me\s+about)\b", re.IGNORECASE),
    ],
}


@dataclass
class EmotionSnapshot:
    """A single emotion reading from a message."""

    state: EmotionState
    confidence: float  # 0.0 - 1.0
    energy: float  # -1.0 (draining) to 1.0 (energizing)


@dataclass
class EmotionContext:
    """Current emotional context for system prompt injection."""

    dominant_emotion: EmotionState = EmotionState.NEUTRAL
    energy_level: int = 70  # 0-100
    trend: str = "stable"  # "rising", "falling", "stable"
    recent_states: list[EmotionState] = field(default_factory=list)


# Energy impact per emotion
_ENERGY_IMPACT: dict[EmotionState, float] = {
    EmotionState.NEUTRAL: 0.0,
    EmotionState.HAPPY: 5.0,
    EmotionState.CURIOUS: 3.0,
    EmotionState.FRUSTRATED: -8.0,
    EmotionState.SAD: -10.0,
    EmotionState.EXCITED: 10.0,
    EmotionState.TIRED: -15.0,
    EmotionState.ANXIOUS: -5.0,
}


class EmotionTracker:
    """Tracks the user's emotional state across conversation turns."""

    def __init__(self, window_size: int = 10) -> None:
        config = get_yaml_config()
        self._enabled = config.get("persona", {}).get("emotion_tracking_enabled", True)
        self._window: deque[EmotionSnapshot] = deque(maxlen=window_size)
        self._energy: float = 70.0  # Start at comfortable baseline

    @property
    def enabled(self) -> bool:
        """Whether emotion tracking is enabled."""
        return self._enabled

    def analyze(self, text: str) -> EmotionSnapshot:
        """Analyze a message for emotional content."""
        scores: dict[EmotionState, float] = {}

        for emotion, patterns in _EMOTION_KEYWORDS.items():
            score = 0.0
            for pattern in patterns:
                matches = pattern.findall(text)
                score += len(matches) * 0.3
            if score > 0:
                scores[emotion] = min(score, 1.0)

        if not scores:
            snapshot = EmotionSnapshot(state=EmotionState.NEUTRAL, confidence=0.5, energy=0.0)
        else:
            dominant = max(scores, key=scores.get)
            snapshot = EmotionSnapshot(
                state=dominant,
                confidence=scores[dominant],
                energy=_ENERGY_IMPACT.get(dominant, 0.0),
            )

        if self._enabled:
            self._window.append(snapshot)
            self._energy = max(0, min(100, self._energy + snapshot.energy))
            logger.debug(
                f"EmotionTracker: {snapshot.state} (confidence={snapshot.confidence:.2f}, energy={self._energy:.0f})"
            )

        return snapshot

    def get_context(self) -> EmotionContext:
        """Get current emotional context for system prompt injection."""
        if not self._window:
            return EmotionContext()

        # Find dominant emotion from recent window
        state_counts: dict[EmotionState, int] = {}
        for snap in self._window:
            state_counts[snap.state] = state_counts.get(snap.state, 0) + 1

        dominant = max(state_counts, key=state_counts.get)

        # Determine trend
        if len(self._window) >= 3:
            recent_energy = [s.energy for s in list(self._window)[-3:]]
            avg_recent = sum(recent_energy) / len(recent_energy)
            if avg_recent > 3:
                trend = "rising"
            elif avg_recent < -3:
                trend = "falling"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return EmotionContext(
            dominant_emotion=dominant,
            energy_level=int(self._energy),
            trend=trend,
            recent_states=[s.state for s in self._window],
        )

    def get_tone_hint(self) -> str:
        """Get a tone adjustment hint for the system prompt.

        Returns empty string if neutral — no adjustment needed.
        """
        ctx = self.get_context()

        if ctx.dominant_emotion == EmotionState.NEUTRAL:
            return ""

        hints = {
            EmotionState.HAPPY: "The user seems in a good mood. Match his energy — be upbeat and engaged.",
            EmotionState.FRUSTRATED: "The user seems frustrated. Be steady, practical, and efficient. Don't add fluff.",
            EmotionState.SAD: "The user seems down. Be warm and present. Empathize before problem-solving.",
            EmotionState.ANXIOUS: "The user seems worried. Be calm and reassuring. Focus on what's controllable.",
            EmotionState.TIRED: "The user seems tired. Keep responses short and easy to process. Don't overwhelm.",
            EmotionState.EXCITED: "The user is excited about something. Share his enthusiasm and build on it.",
            EmotionState.CURIOUS: "The user is in exploration mode. Engage deeply with the topic.",
        }

        hint = hints.get(ctx.dominant_emotion, "")
        if ctx.energy_level < 30:
            hint += " Energy is low — keep it concise."
        elif ctx.energy_level > 80:
            hint += " Energy is high — feel free to be more expressive."

        return hint


# Module singleton
_tracker: EmotionTracker | None = None


def get_emotion_tracker() -> EmotionTracker:
    """Get or create the EmotionTracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = EmotionTracker()
    return _tracker
