"""Pattern Learner — silently learns the user's behavioral patterns from conversation history.

Fully automatic, silent — learns patterns without telling the user.
Stores patterns as facts in ChromaDB knowledge collection.
Designed to run periodically (weekly or on-demand).
"""

import time
from collections import Counter
from datetime import datetime

from loguru import logger


def analyze_activity_patterns(turns: list[dict]) -> dict:
    """Analyze conversation turns for temporal activity patterns.

    Args:
        turns: List of {"role", "content", "timestamp"} dicts

    Returns:
        Pattern dict with detected behaviors
    """
    if not turns:
        return {}

    patterns = {}

    # Filter user turns only
    user_turns = [t for t in turns if t.get("role") == "user" and t.get("timestamp")]

    if not user_turns:
        return {}

    # Analyze wake times (first message of each day)
    daily_first = {}
    for turn in user_turns:
        ts = turn["timestamp"]
        dt = datetime.fromtimestamp(ts)
        day_key = dt.strftime("%Y-%m-%d")
        if day_key not in daily_first or ts < daily_first[day_key]:
            daily_first[day_key] = ts

    if daily_first:
        wake_hours = []
        for ts in daily_first.values():
            dt = datetime.fromtimestamp(ts)
            wake_hours.append(dt.hour + dt.minute / 60.0)
        if wake_hours:
            avg_wake = sum(wake_hours) / len(wake_hours)
            patterns["typical_wake_hour"] = round(avg_wake, 1)

    # Analyze peak activity hours
    hour_counts = Counter()
    for turn in user_turns:
        dt = datetime.fromtimestamp(turn["timestamp"])
        hour_counts[dt.hour] += 1

    if hour_counts:
        peak_hours = hour_counts.most_common(3)
        patterns["peak_activity_hours"] = [h for h, _ in peak_hours]

    # Analyze topic frequency (simple word counting)
    word_counts = Counter()
    for turn in user_turns:
        words = turn.get("content", "").lower().split()
        for word in words:
            if len(word) > 4:  # Skip short/common words
                word_counts[word] += 1

    if word_counts:
        patterns["frequent_topics"] = [w for w, _ in word_counts.most_common(10)]

    # Analyze message length patterns
    lengths = [len(t.get("content", "")) for t in user_turns]
    if lengths:
        patterns["avg_message_length"] = round(sum(lengths) / len(lengths))
        patterns["prefers_brief"] = patterns["avg_message_length"] < 50

    # Analyze day-of-week activity
    dow_counts = Counter()
    for turn in user_turns:
        dt = datetime.fromtimestamp(turn["timestamp"])
        dow_counts[dt.strftime("%A")] += 1
    if dow_counts:
        patterns["most_active_days"] = [d for d, _ in dow_counts.most_common(3)]

    return patterns


def format_patterns_as_facts(patterns: dict) -> list[dict]:
    """Convert pattern analysis into storable fact dicts."""
    facts = []
    now = time.time()

    if "typical_wake_hour" in patterns:
        hour = patterns["typical_wake_hour"]
        hour_int = int(hour)
        minute = int((hour - hour_int) * 60)
        facts.append(
            {
                "content": f"The user typically starts his day around {hour_int}:{minute:02d}",
                "metadata": {
                    "source": "pattern_analysis",
                    "timestamp": now,
                    "category": "personal.routine",
                    "confidence": 0.7,
                    "pattern_type": "wake_time",
                },
            }
        )

    if "peak_activity_hours" in patterns:
        hours = patterns["peak_activity_hours"]
        hour_strs = [f"{h}:00" for h in hours]
        facts.append(
            {
                "content": f"The user is most active around {', '.join(hour_strs)}",
                "metadata": {
                    "source": "pattern_analysis",
                    "timestamp": now,
                    "category": "personal.routine",
                    "confidence": 0.6,
                    "pattern_type": "peak_hours",
                },
            }
        )

    if "most_active_days" in patterns:
        days = patterns["most_active_days"]
        facts.append(
            {
                "content": f"The user is most active on {', '.join(days)}",
                "metadata": {
                    "source": "pattern_analysis",
                    "timestamp": now,
                    "category": "personal.routine",
                    "confidence": 0.6,
                    "pattern_type": "active_days",
                },
            }
        )

    if "prefers_brief" in patterns:
        style = "brief, concise messages" if patterns["prefers_brief"] else "detailed, longer messages"
        facts.append(
            {
                "content": f"The user tends to write {style} (avg {patterns.get('avg_message_length', 0)} chars)",
                "metadata": {
                    "source": "pattern_analysis",
                    "timestamp": now,
                    "category": "personal.preferences",
                    "confidence": 0.5,
                    "pattern_type": "message_style",
                },
            }
        )

    return facts


async def run_pattern_analysis() -> list[dict]:
    """Run pattern analysis on recent conversation history.

    Returns list of extracted pattern facts.
    """
    try:
        from src.memory.store import get_recent_turns

        turns = await get_recent_turns(limit=500)
        if not turns:
            logger.info("PatternLearner: no turns to analyze")
            return []

        patterns = analyze_activity_patterns(turns)
        facts = format_patterns_as_facts(patterns)
        logger.info(f"PatternLearner: extracted {len(facts)} patterns from {len(turns)} turns")
        return facts
    except Exception as e:
        logger.error(f"PatternLearner: analysis failed: {e}")
        return []
