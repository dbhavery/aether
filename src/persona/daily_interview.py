"""Daily interview — Aether initiates a conversation to learn the user's preferences.

Fires at 7PM via APScheduler. Checks for activity before interrupting.
Questions are drawn from a pool, tracked to avoid repetition.
"""

import random
from pathlib import Path

from loguru import logger

from src.core.events import event_bus
from src.shared.config import get_settings, get_yaml_config
from src.shared.types import EventType, AetherEvent

# Question pool — cycled in random order, tracked to avoid repeats
INTERVIEW_QUESTIONS: list[str] = [
    "What's been the best part of your day so far?",
    "Is there anything you'd like me to remind you about tomorrow?",
    "Have you been working on any projects I should know about?",
    "Is there a topic you'd like me to research for you?",
    "What kind of music are you in the mood for lately?",
    "Are there any upcoming events or deadlines I should track?",
    "How are you feeling about the balance between work and downtime?",
    "Is there anything about how I respond that you'd like me to adjust?",
    "What's something new you've learned or been thinking about recently?",
    "Are there any friends or contacts you want me to help you keep in touch with?",
    "Is there a skill or hobby you've been wanting to pick up?",
    "What's your energy level been like this week?",
    "Do you have any travel plans I should help organize?",
    "Is there something that's been bugging you that I can help with?",
    "What would make tomorrow a great day for you?",
]

# Track which questions have been asked (persists across scheduler calls via file)
_asked_file: Path | None = None


def _get_asked_file() -> Path:
    """Lazily resolve asked file path — avoids calling get_settings() at import time."""
    global _asked_file
    if _asked_file is None:
        _asked_file = Path(get_settings().aether_data_path) / "interview_asked.txt"
    return _asked_file


def _get_asked_questions() -> set[str]:
    path = _get_asked_file()
    if path.exists():
        return set(path.read_text().strip().splitlines())
    return set()


def _mark_question_asked(question: str) -> None:
    asked = _get_asked_questions()
    asked.add(question)
    path = _get_asked_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(asked)))


def _pick_question() -> str:
    """Pick a question that hasn't been asked recently. Resets pool when exhausted."""
    asked = _get_asked_questions()
    available = [q for q in INTERVIEW_QUESTIONS if q not in asked]
    if not available:
        # Reset the pool
        _get_asked_file().unlink(missing_ok=True)
        available = INTERVIEW_QUESTIONS.copy()
    question = random.choice(available)  # noqa: S311  # nosec B311
    _mark_question_asked(question)
    return question


async def start_interview_session() -> None:
    """Initiate a daily interview session.

    Called by APScheduler at the configured time (default 7PM).
    Checks max_proactive limit before sending.
    """
    try:
        config = get_yaml_config()
        notifications_config = config.get("notifications", {})
        max_proactive = notifications_config.get("max_proactive_per_day", 3)

        if max_proactive == 0:
            logger.info("DailyInterview: proactive messages disabled (max=0)")
            return

        # Check if The user is available before interrupting
        from src.persona.busy_detector import get_busy_detector

        detector = get_busy_detector()
        availability = detector.get_availability()
        if availability in ("sleeping", "likely_busy"):
            logger.info(f"DailyInterview: skipped — The user is {availability}")
            return

        question = _pick_question()
        greeting = f"Hey there — just checking in. {question}"

        await event_bus.publish(
            AetherEvent(
                type=EventType.PROACTIVE_MESSAGE,
                data={
                    "text": greeting,
                    "category": "daily_interview",
                    "question": question,
                },
                source_module="daily_interview",
            )
        )

        logger.info(f"DailyInterview: sent question — {question[:60]}")

    except Exception as e:
        logger.error(f"DailyInterview: failed to start session: {e}")
