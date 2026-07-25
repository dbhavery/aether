"""LLM routing — Aether decides which model to use. The user never sees this happen.

Three-tier routing:
1. Instant match — regex patterns for obvious categories (greetings, code keywords)
2. Keyword match — broader regex patterns (realtime, research, summarize)
3. LLM classification — when no keyword matches, ask qwen3:8b to classify
"""

import re
from collections import OrderedDict

from loguru import logger


class LLMTier:
    FAST = "fast"  # qwen3:8b local — greetings, intent, quick responses
    CLAUDE = "claude"  # claude-sonnet-4-6 — general conversation, reasoning
    CLAUDE_HEAVY = "claude_heavy"  # claude-opus-4-6 — coding, complex analysis
    GEMINI = "gemini"  # gemini-2.5-flash — real-time, search grounding
    GEMINI_FAST = "gemini_fast"  # gemini-2.0-flash-lite — summarization
    GEMINI_PRO = "gemini_pro"  # gemini-2.5-pro — deep research


# Keyword patterns for routing
_FAST_PATTERNS = re.compile(
    r"^(hi|hello|hey|thanks|thank you|ok|okay|sure|yes|no|bye|goodbye|good morning|good night)[\s!.]*$",
    re.IGNORECASE,
)
_CODING_PATTERNS = re.compile(
    r"\b(code|function|class|debug|error|exception|python|javascript|typescript|sql|api|refactor|implement|fix the|write a)\b",
    re.IGNORECASE,
)
_REALTIME_PATTERNS = re.compile(
    r"\b(weather|news|today|tonight|current|latest|right now|what time|stock|price|score)\b",
    re.IGNORECASE,
)
_SUMMARIZE_PATTERNS = re.compile(
    r"\b(summarize|summary|tldr|brief|overview|recap)\b",
    re.IGNORECASE,
)
_DEEP_RESEARCH_PATTERNS = re.compile(
    r"\b(research|analyze|compare|deep dive|comprehensive|detailed analysis|report on)\b",
    re.IGNORECASE,
)

# LRU cache for LLM-based classifications (max 100 entries)
_CLASSIFICATION_CACHE_MAX = 100
_classification_cache: OrderedDict[str, str] = OrderedDict()

# Mapping from LLM classification output to LLMTier
_CLASSIFICATION_MAP: dict[str, str] = {
    "greeting": LLMTier.FAST,
    "general": LLMTier.CLAUDE,
    "code": LLMTier.CLAUDE_HEAVY,
    "research": LLMTier.GEMINI_PRO,
    "realtime": LLMTier.GEMINI,
    "deep_research": LLMTier.GEMINI_PRO,
    "summarize": LLMTier.GEMINI_FAST,
}

_CLASSIFICATION_PROMPT = (
    "Classify this user message into exactly one category. "
    "Reply with a single word, nothing else.\n"
    "Categories: greeting, general, code, research, realtime, summarize\n\n"
    "Message: {text}"
)


def _cache_get(key: str) -> str | None:
    """Get from LRU classification cache."""
    if key in _classification_cache:
        _classification_cache.move_to_end(key)
        return _classification_cache[key]
    return None


def _cache_put(key: str, value: str) -> None:
    """Put into LRU classification cache, evicting oldest if full."""
    _classification_cache[key] = value
    _classification_cache.move_to_end(key)
    while len(_classification_cache) > _CLASSIFICATION_CACHE_MAX:
        _classification_cache.popitem(last=False)


async def _classify_with_llm(text: str) -> str:
    """Use qwen3:8b to classify an ambiguous message. Returns LLMTier string."""
    # Check cache first
    cache_key = text.strip().lower()[:200]
    cached = _cache_get(cache_key)
    if cached:
        logger.debug(f"Router: LLM classification cache hit -> {cached}")
        return cached

    try:
        import aiohttp

        from src.shared.config import get_settings, get_yaml_config
        from src.shared.http_client import get_shared_session

        settings = get_settings()
        yaml_config = get_yaml_config()
        model_name = yaml_config["llm"]["fast_model"]
        url = f"{settings.ollama_base_url}/api/chat"
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": _CLASSIFICATION_PROMPT.format(text=text[:500])}],
            "stream": False,
            "options": {"num_predict": 10},
        }

        session = await get_shared_session()
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
            if resp.status != 200:
                logger.warning(f"Router: LLM classification failed (HTTP {resp.status})")
                return LLMTier.CLAUDE
            data = await resp.json()
            raw = data.get("message", {}).get("content", "").strip().lower()
            # Strip <think> tags from thinking models (qwen3)
            raw = re.sub(r"<think>[\s\S]*?</think>\s*", "", raw).strip()
            # Extract the first word as the classification
            words = raw.split()
            classification = words[0].rstrip(".,!") if words else "general"

        tier = _CLASSIFICATION_MAP.get(classification, LLMTier.CLAUDE)
        _cache_put(cache_key, tier)
        logger.debug(f"Router: LLM classified '{text[:40]}' as '{classification}' -> {tier}")
        return tier
    except Exception as e:
        logger.warning(f"Router: LLM classification error ({e}) — defaulting to CLAUDE")
        return LLMTier.CLAUDE


def route(text: str, force_tier: str | None = None) -> str:
    """Route a message to the correct LLM tier (sync — keyword matching only).

    For the async LLM classification fallback, use route_async().
    """
    if force_tier:
        logger.debug(f"Router: forced tier = {force_tier}")
        return force_tier

    if _FAST_PATTERNS.match(text.strip()):
        tier = LLMTier.FAST
    elif _CODING_PATTERNS.search(text):
        tier = LLMTier.CLAUDE_HEAVY
    elif _REALTIME_PATTERNS.search(text):
        tier = LLMTier.GEMINI
    elif _DEEP_RESEARCH_PATTERNS.search(text):
        tier = LLMTier.GEMINI_PRO
    elif _SUMMARIZE_PATTERNS.search(text):
        tier = LLMTier.GEMINI_FAST
    else:
        tier = LLMTier.CLAUDE

    logger.debug(f"Router: '{text[:50]}' -> {tier}")
    return tier


async def route_async(text: str, force_tier: str | None = None) -> str:
    """Route with LLM classification fallback for ambiguous messages.

    Fallback chain: instant match → keyword → LLM classification → default CLAUDE.
    """
    if force_tier:
        logger.debug(f"Router: forced tier = {force_tier}")
        return force_tier

    # Tier 1: Instant match (regex)
    if _FAST_PATTERNS.match(text.strip()):
        tier = LLMTier.FAST
        logger.debug(f"Router: '{text[:50]}' -> {tier} (instant)")
        return tier

    # Tier 2: Keyword match (regex)
    if _CODING_PATTERNS.search(text):
        tier = LLMTier.CLAUDE_HEAVY
    elif _REALTIME_PATTERNS.search(text):
        tier = LLMTier.GEMINI
    elif _DEEP_RESEARCH_PATTERNS.search(text):
        tier = LLMTier.GEMINI_PRO
    elif _SUMMARIZE_PATTERNS.search(text):
        tier = LLMTier.GEMINI_FAST
    else:
        tier = None

    if tier:
        logger.debug(f"Router: '{text[:50]}' -> {tier} (keyword)")
        return tier

    # Tier 3: LLM classification fallback
    tier = await _classify_with_llm(text)
    logger.debug(f"Router: '{text[:50]}' -> {tier} (llm)")
    return tier
