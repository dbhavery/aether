"""Fact Extractor — extracts weighted important facts from conversations.

NO summarization. Extracts facts in two modes:
- Explicit: "remember this" / "don't forget" → immediate, importance=1.0
- Batch: every N turns, run qwen3:8b extraction in background

Dual fact format:
- Structured KV for known categories
- Natural language for nuanced/contextual facts

Source tracking: every fact tagged with source type + timestamp.
Contradiction handling: stores both old and new, uses most recent.
"""

import re
import time

from loguru import logger

from src.shared.config import get_yaml_config

# Patterns that indicate explicit memory requests
_EXPLICIT_PATTERNS = [
    re.compile(r"remember\s+(?:that\s+)?(.+)", re.IGNORECASE),
    re.compile(r"don'?t\s+forget\s+(?:that\s+)?(.+)", re.IGNORECASE),
    re.compile(r"keep\s+in\s+mind\s+(?:that\s+)?(.+)", re.IGNORECASE),
    re.compile(r"note\s+(?:that\s+)?(.+)", re.IGNORECASE),
    re.compile(r"for\s+(?:future\s+)?reference[,:]?\s*(.+)", re.IGNORECASE),
]

# Known structured categories for KV extraction
_STRUCTURED_CATEGORIES = {
    "favorite_food",
    "favorite_color",
    "favorite_music",
    "favorite_movie",
    "birthday",
    "allergy",
    "medication",
    "work_project",
    "meeting",
    "deadline",
    "preference",
    "dislike",
    "friend_name",
    "family_member",
    "pet",
    "hobby",
    "goal",
    "routine",
    "location",
    "contact",
}

# Extraction prompt for batch processing via qwen3:8b
_EXTRACTION_PROMPT = """Extract important facts from this conversation. Return JSON array of facts.

For each fact:
- "content": the fact as a natural sentence
- "subject": who/what (usually "User")
- "category": one of: personal.preferences, personal.health, personal.goals, social.friends, social.family, work.projects, work.meetings, technical.code, technical.tools
- "confidence": 0.0-1.0
- "is_correction": true if this corrects a previous statement

Only extract MEANINGFUL facts. Skip greetings, fillers, small talk.

Conversation:
{conversation}

JSON facts:"""


def detect_explicit_memory(text: str) -> tuple[bool, str]:
    """Check if text contains an explicit memory request.

    Returns (is_explicit, extracted_fact_text).
    """
    for pattern in _EXPLICIT_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, match.group(1).strip()
    return False, ""


class FactExtractor:
    """Extracts facts from conversations in dual format."""

    # Maximum turns to keep in buffer (prevents unbounded growth)
    _MAX_BUFFER_SIZE = 100

    def __init__(self, batch_interval: int = 10):
        self.batch_interval = batch_interval
        self._turn_buffer: list[dict] = []
        self._turn_count_since_extract: int = 0

    def add_turn(self, role: str, content: str, timestamp: float | None = None) -> list[dict]:
        """Add a conversation turn. Returns any immediately-extracted facts.

        Explicit memory requests are extracted immediately.
        Regular turns are buffered for batch extraction.
        """
        ts = timestamp or time.time()
        self._turn_buffer.append({"role": role, "content": content, "timestamp": ts})
        self._turn_count_since_extract += 1

        # Trim buffer to prevent unbounded growth
        if len(self._turn_buffer) > self._MAX_BUFFER_SIZE:
            self._turn_buffer = self._turn_buffer[-self._MAX_BUFFER_SIZE :]

        # Check for explicit memory requests in user messages
        immediate_facts = []
        if role == "user":
            is_explicit, fact_text = detect_explicit_memory(content)
            if is_explicit and fact_text:
                fact = {
                    "content": fact_text,
                    "metadata": {
                        "source": "explicit",
                        "timestamp": ts,
                        "importance": 1.0,
                        "explicit_flag": True,
                    },
                }
                immediate_facts.append(fact)
                logger.info(f"FactExtractor: explicit fact — '{fact_text[:60]}'")

        return immediate_facts

    def should_batch_extract(self) -> bool:
        """Check if we've accumulated enough turns for a batch extraction."""
        return self._turn_count_since_extract >= self.batch_interval

    def get_batch_prompt(self) -> str | None:
        """Build the extraction prompt from buffered turns.

        Returns None if not enough turns accumulated.
        """
        if not self.should_batch_extract():
            return None

        conversation_text = "\n".join(
            f"{t['role'].upper()}: {t['content']}" for t in self._turn_buffer[-self.batch_interval :]
        )

        return _EXTRACTION_PROMPT.format(conversation=conversation_text)

    def parse_extraction_result(self, llm_response: str, source: str = "conversation") -> list[dict]:
        """Parse LLM extraction response into fact dicts.

        Handles both clean JSON and JSON embedded in text/markdown.
        """
        import json

        facts = []
        try:
            # Try to extract JSON array from response
            json_match = re.search(r"\[[\s\S]*\]", llm_response)
            if json_match:
                raw_facts = json.loads(json_match.group())
            else:
                logger.warning("FactExtractor: no JSON array found in extraction response")
                return []

            for raw in raw_facts:
                if not isinstance(raw, dict):
                    continue
                content = raw.get("content", "")
                if not content or len(content) < 5:
                    continue

                fact = {
                    "content": content,
                    "metadata": {
                        "source": source,
                        "timestamp": time.time(),
                        "subject": raw.get("subject", "User"),
                        "category": raw.get("category", ""),
                        "confidence": min(1.0, max(0.0, float(raw.get("confidence", 0.5)))),
                        "is_correction": bool(raw.get("is_correction", False)),
                    },
                }
                facts.append(fact)

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"FactExtractor: failed to parse extraction result: {e}")

        logger.info(f"FactExtractor: batch extracted {len(facts)} facts from {source}")
        return facts

    def clear_buffer(self) -> None:
        """Clear the turn buffer."""
        self._turn_buffer.clear()
        self._turn_count_since_extract = 0


async def run_batch_extraction(extractor: FactExtractor) -> list[dict]:
    """Run batch fact extraction using qwen3:8b (local, fast).

    Returns list of extracted fact dicts.
    """
    prompt = extractor.get_batch_prompt()
    if prompt is None:
        return []

    try:
        from src.brain.clients import call_ollama

        yaml_config = get_yaml_config()
        model = yaml_config.get("llm", {}).get("fast_model", "qwen3:8b")
        response = await call_ollama(prompt=prompt, model=model)
        facts = extractor.parse_extraction_result(response)
        extractor._turn_count_since_extract = 0  # Reset only on success
        return facts
    except Exception as e:
        logger.error(f"FactExtractor: batch extraction failed: {e}")
        return []
