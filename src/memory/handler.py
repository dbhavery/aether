"""Memory event handler — bridges EventBus to the memory store.

Integrates: ChromaDB storage, 3-tier manager, fact extraction, categorization.
"""

import asyncio

from loguru import logger

from src.core.events import event_bus
from src.memory.categorizer import classify
from src.memory.embeddings import EmbeddingsUnavailable
from src.memory.fact_extractor import FactExtractor, run_batch_extraction
from src.memory.store import store_conversation_turn, store_fact
from src.memory.tier_manager import get_tier_manager
from src.shared.types import AetherEvent, EventType

# Phrases that indicate error/system messages — don't pollute long-term memory
_ERROR_PHRASES = frozenset(
    {
        "Something went wrong on my end",
        "I'm taking longer than usual to think",
        "I ran into an issue with that",
    }
)

# Module-level fact extractor (batch every 10 turns)
_fact_extractor = FactExtractor(batch_interval=10)
# Track background tasks to prevent GC
_bg_tasks: set[asyncio.Task] = set()


async def _store_with_tiers(role: str, text: str, timestamp: float) -> None:
    """Store turn in ChromaDB and feed to tier manager + categorizer."""
    # Store in ChromaDB (existing path)
    await store_conversation_turn(role, text, timestamp)

    # Categorize and store in tier manager
    try:
        category = await classify(text, use_llm_fallback=False)
        tier_mgr = get_tier_manager()
        tier_mgr.store(
            item_id=f"{role}:{timestamp:.0f}",
            item={
                "content": text,
                "metadata": {
                    "role": role,
                    "timestamp": timestamp,
                    "category": category,
                },
            },
        )
    except Exception as e:
        logger.warning(f"Memory: tier storage failed (non-blocking): {e}")


async def _process_facts(role: str, text: str, timestamp: float) -> None:
    """Feed turn to fact extractor. Store immediate facts and trigger batch extraction."""
    immediate_facts = _fact_extractor.add_turn(role, text, timestamp)

    # Store any explicitly requested facts immediately
    for fact in immediate_facts:
        try:
            category = await classify(fact["content"], use_llm_fallback=False)
            fact["metadata"]["category"] = category
            await store_fact(
                key=f"explicit:{timestamp:.0f}",
                value=fact["content"],
                importance=fact["metadata"].get("importance", 1.0),
            )
            tier_mgr = get_tier_manager()
            tier_mgr.store(f"fact:explicit:{timestamp:.0f}", fact)
        except Exception as e:
            logger.warning(f"Memory: explicit fact storage failed: {e}")

    # Trigger batch extraction in background if enough turns accumulated
    if _fact_extractor.should_batch_extract():
        _bg_task = asyncio.create_task(_run_batch_extraction_bg())  # fire-and-forget background task
        _bg_tasks.add(_bg_task)
        _bg_task.add_done_callback(_bg_tasks.discard)


async def _run_batch_extraction_bg() -> None:
    """Background batch fact extraction."""
    try:
        facts = await run_batch_extraction(_fact_extractor)
        tier_mgr = get_tier_manager()
        for i, fact in enumerate(facts):
            category = await classify(fact["content"], use_llm_fallback=False)
            fact["metadata"]["category"] = category
            fact_id = f"fact:batch:{fact['metadata'].get('timestamp', 0):.0f}:{i}"
            await store_fact(
                key=fact_id,
                value=fact["content"],
                importance=fact["metadata"].get("confidence", 0.5),
            )
            tier_mgr.store(fact_id, fact)
        if facts:
            logger.info(f"Memory: batch extraction stored {len(facts)} facts")
    except Exception as e:
        logger.error(f"Memory: batch extraction failed: {e}")


async def on_user_message(event: AetherEvent) -> None:
    text = event.data.get("text", "")
    timestamp = event.timestamp
    if not text:
        return
    try:
        await _store_with_tiers("user", text, timestamp)
        await _process_facts("user", text, timestamp)
    except EmbeddingsUnavailable as exc:
        logger.debug(f"Memory: skipping user-turn storage (embeddings unavailable): {exc}")


async def on_response_ready(event: AetherEvent) -> None:
    text = event.data.get("text", "")
    timestamp = event.timestamp
    if not text or event.data.get("is_interim", False):
        return
    # Skip error/apologetic responses — they don't add value to memory
    if any(phrase in text for phrase in _ERROR_PHRASES):
        logger.debug(f"Memory: skipping error response from storage: '{text[:60]}'")
        return
    try:
        await _store_with_tiers("assistant", text, timestamp)
        await _process_facts("assistant", text, timestamp)
    except EmbeddingsUnavailable as exc:
        logger.debug(f"Memory: skipping assistant-turn storage (embeddings unavailable): {exc}")


def register_memory_handlers() -> None:
    event_bus.subscribe(EventType.USER_MESSAGE, on_user_message)
    event_bus.subscribe(EventType.RESPONSE_TEXT_READY, on_response_ready)
    logger.info("Memory: handlers registered")
