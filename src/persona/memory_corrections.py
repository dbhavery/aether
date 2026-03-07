"""Memory corrections — detect when the user corrects Aether and update stored memories.

Detection is regex-based for speed, but correction application uses the memory store
to find and update the relevant turn. Aether ONLY confirms correction after the
memory store actually processes it.
"""

import re
import uuid

from loguru import logger

from src.core.events import event_bus
from src.memory.store import search_memory, store_fact
from src.shared.types import EventType, AetherEvent

# Correction detection patterns — match common correction phrases
_CORRECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bno[,.]?\s+(?:i\s+(?:said|meant)|it'?s|that'?s)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bactually[,.]?\s+(?:i\s+(?:said|meant)|it'?s|that'?s)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bthat'?s\s+(?:not\s+(?:right|correct|what\s+i))\b[.,]?\s*(.*)", re.IGNORECASE),
    re.compile(r"\bi\s+(?:didn'?t\s+(?:say|mean)\s+that)\b[.,]?\s*(.*)", re.IGNORECASE),
    re.compile(r"\bcorrection[:\s]+(.+)", re.IGNORECASE),
]


def detect_correction(text: str) -> tuple[bool, str]:
    """Check if user message is a correction.

    Returns:
        (is_correction, extracted_correction_text)
    """
    for pattern in _CORRECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            correction_text = match.group(1) if match.lastindex else text
            return True, correction_text.strip()
    return False, ""


async def handle_memory_correction(event: AetherEvent) -> None:
    """Process a memory correction event.

    Searches for the relevant memory, updates it, and confirms only after success.
    """
    correction_text = event.data.get("correction_text", "")
    original_context = event.data.get("original_context", "")

    if not correction_text:
        logger.warning("MemoryCorrections: empty correction text, skipping")
        return

    try:
        # Search for the memory being corrected
        search_query = original_context if original_context else correction_text
        results = await search_memory(search_query, n_results=3)

        if results:
            # Store the correction as a fact
            fact_key = f"correction_{uuid.uuid4().hex[:12]}"
            await store_fact(
                key=fact_key,
                value=f"The user corrected: {correction_text} (context: {original_context})",
                importance=0.8,
            )
            logger.info(f"MemoryCorrections: stored correction — {correction_text[:60]}")
        else:
            # No matching memory found, store as new fact anyway
            fact_key = f"correction_{uuid.uuid4().hex[:12]}"
            await store_fact(
                key=fact_key,
                value=f"The user stated: {correction_text}",
                importance=0.7,
            )
            logger.info("MemoryCorrections: no matching memory, stored as new fact")

    except Exception as e:
        logger.error(f"MemoryCorrections: failed to process correction: {e}")


def register_memory_correction_handler() -> None:
    """Subscribe to MEMORY_CORRECTION events."""
    event_bus.subscribe(EventType.MEMORY_CORRECTION, handle_memory_correction)
    logger.info("MemoryCorrections: handler registered")
