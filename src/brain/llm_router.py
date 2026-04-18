"""Tier-based LLM router backed by litellm.

Brain code never asks for a specific model — it asks for a tier (FAST/MAIN/HEAVY).
The tier is resolved to an actual model string through the user's config. This file
does two things:

1. **Complexity routing:** given a user message, decide which tier should handle it.
   Three levels per docs/LLM-PROVIDERS.md §4:

     - Level 1 — instant regex (greetings / single-word -> FAST)
     - Level 2 — keyword regex (research/analyze/code -> HEAVY; weather/news/today -> MAIN)
     - Level 3 — LLM classification via the FAST tier (async only, LRU-100 cached)

2. **Model resolution:** map a Tier to the litellm-format model string from the user's
   `llm.tier_map` in config, applying provider presets as the default.

Provider selection, key storage, and the actual litellm call live in ``llm_client.py``.
This module is pure policy; it never makes an LLM call directly except inside
``route_complexity_async`` when level-3 classification is needed — and that path calls
through ``llm_client.complete`` so provider choice stays centralised.

See:
    docs/LLM-PROVIDERS.md §3 (tier table), §4 (complexity routing)
"""

from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Mapping


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class Tier(StrEnum):
    """Abstract complexity tiers. Brain code routes by these, never by model name."""

    FAST = "fast"
    MAIN = "main"
    HEAVY = "heavy"


# ---------------------------------------------------------------------------
# Provider presets — docs/LLM-PROVIDERS.md §3
#
# Each value is a litellm-format model string. Users pick a provider in the
# onboarding wizard; we seed their tier_map from the matching preset. They can
# override any of these in Sandbox -> LLM settings afterwards.
# ---------------------------------------------------------------------------

TIER_PRESETS: Final[Mapping[str, Mapping[Tier, str]]] = {
    "ollama": {
        Tier.FAST: "ollama/qwen2.5:7b",
        Tier.MAIN: "ollama/qwen2.5:14b",
        Tier.HEAVY: "ollama/qwen2.5:32b",
    },
    "anthropic": {
        Tier.FAST: "anthropic/claude-haiku-4-5",
        Tier.MAIN: "anthropic/claude-sonnet-4-6",
        Tier.HEAVY: "anthropic/claude-opus-4-7",
    },
    "openai": {
        Tier.FAST: "openai/gpt-5-mini",
        Tier.MAIN: "openai/gpt-5",
        Tier.HEAVY: "openai/gpt-5-thinking",
    },
    "google": {
        Tier.FAST: "gemini/gemini-2.5-flash-lite",
        Tier.MAIN: "gemini/gemini-2.5-flash",
        Tier.HEAVY: "gemini/gemini-2.5-pro",
    },
    "groq": {
        Tier.FAST: "groq/llama-3.3-70b-versatile",
        Tier.MAIN: "groq/llama-3.3-70b-versatile",
        Tier.HEAVY: "groq/llama-3.3-70b-versatile",
    },
    "openrouter": {
        Tier.FAST: "openrouter/google/gemini-flash-1.5",
        Tier.MAIN: "openrouter/anthropic/claude-sonnet-4-6",
        Tier.HEAVY: "openrouter/anthropic/claude-opus-4-7",
    },
    "guest": {
        Tier.FAST: "groq/llama-3.3-70b-versatile",
        Tier.MAIN: "groq/llama-3.3-70b-versatile",
        Tier.HEAVY: "groq/llama-3.3-70b-versatile",
    },
}

DEFAULT_PROVIDER: Final[str] = "ollama"


def get_default_tier_map(provider: str) -> dict[Tier, str]:
    """Return the preset tier_map for a provider. Unknown provider -> Ollama preset.

    Used by the onboarding wizard to seed a user's config after they pick a provider.
    """
    preset = TIER_PRESETS.get(provider.lower())
    if preset is None:
        logger.warning(f"LLMRouter: unknown provider '{provider}', seeding with Ollama preset")
        preset = TIER_PRESETS[DEFAULT_PROVIDER]
    return dict(preset)


# ---------------------------------------------------------------------------
# Level-1 and Level-2 regex patterns
#
# Kept conservative on purpose: these fire deterministically and route to the
# cheapest tier that satisfies the request. Anything that doesn't match falls
# through to MAIN (the sane default) or, in the async path, to LLM classification.
# ---------------------------------------------------------------------------

_GREETING_RE = re.compile(
    r"^(hi|hello|hey|howdy|yo|sup|thanks|thank you|ok|okay|sure|yes|yeah|yep|no|nope|"
    r"bye|goodbye|cya|see ya|good morning|good night|good evening|good afternoon|"
    r"nice|cool|great|awesome|perfect|got it)[\s!.?]*$",
    re.IGNORECASE,
)
_SINGLE_WORD_RE = re.compile(r"^\s*\w{1,24}\s*[!.?]*\s*$")

_HEAVY_KEYWORDS_RE = re.compile(
    r"\b(research|analy[sz]e|analysis|compare|comparison|deep|deep[- ]dive|"
    r"comprehensive|detailed|in[- ]depth|thorough|refactor|architect|design a|"
    r"explain|derive|prove|implement|write (?:a|the) (?:function|class|module|script|program)|"
    r"code|debug|complex)\b",
    re.IGNORECASE,
)
_MAIN_REALTIME_KEYWORDS_RE = re.compile(
    r"\b(weather|news|today|tonight|current|currently|latest|right now|"
    r"what (?:time|date|day)|stock|price|score|forecast|search)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Level-3 classifier — LRU cache + prompt
# ---------------------------------------------------------------------------

_CLASSIFICATION_CACHE_MAX: Final[int] = 100
_classification_cache: OrderedDict[str, Tier] = OrderedDict()
_classification_lock = asyncio.Lock()

_CLASSIFIER_PROMPT: Final[str] = (
    "Classify this user message into exactly one tier. Reply with a single word, "
    "nothing else.\n"
    "Tiers:\n"
    "  fast  - trivial: greetings, one-word replies, yes/no, acknowledgements\n"
    "  main  - general conversation, everyday questions, short requests\n"
    "  heavy - complex reasoning: research, analysis, coding, long-form writing\n\n"
    "Message: {text}\n"
    "Tier:"
)

_VALID_TIERS: Final[frozenset[str]] = frozenset({t.value for t in Tier})


def _cache_get(key: str) -> Tier | None:
    """LRU get; moves the key to the most-recently-used position on hit."""
    if key in _classification_cache:
        _classification_cache.move_to_end(key)
        return _classification_cache[key]
    return None


def _cache_put(key: str, tier: Tier) -> None:
    """LRU put; evicts the oldest entry if over capacity."""
    _classification_cache[key] = tier
    _classification_cache.move_to_end(key)
    while len(_classification_cache) > _CLASSIFICATION_CACHE_MAX:
        _classification_cache.popitem(last=False)


def _cache_key(text: str) -> str:
    return text.strip().lower()[:200]


def clear_classification_cache() -> None:
    """Wipe the LRU classification cache. Intended for tests and provider swaps."""
    _classification_cache.clear()


# ---------------------------------------------------------------------------
# Level-1 + Level-2 synchronous routing
# ---------------------------------------------------------------------------


def route_complexity(text: str) -> Tier:
    """Deterministic tier routing based on regex alone.

    Use this when you must not make a network call (e.g. inside a tight loop or
    pre-warm path). For better accuracy on ambiguous messages, use
    :func:`route_complexity_async`, which adds level-3 LLM classification.

    Decision order:
      1. Greeting / single-word / empty  -> FAST
      2. Contains heavy keywords         -> HEAVY
      3. Contains realtime keywords      -> MAIN
      4. Otherwise                       -> MAIN  (sane default, avoids FAST under-routing)
    """
    stripped = text.strip()
    if not stripped:
        return Tier.FAST

    if _GREETING_RE.match(stripped) or _SINGLE_WORD_RE.match(stripped):
        logger.debug(f"LLMRouter: '{stripped[:40]}' -> FAST (level 1)")
        return Tier.FAST

    if _HEAVY_KEYWORDS_RE.search(stripped):
        logger.debug(f"LLMRouter: '{stripped[:40]}' -> HEAVY (level 2: heavy keyword)")
        return Tier.HEAVY

    if _MAIN_REALTIME_KEYWORDS_RE.search(stripped):
        logger.debug(f"LLMRouter: '{stripped[:40]}' -> MAIN (level 2: realtime keyword)")
        return Tier.MAIN

    logger.debug(f"LLMRouter: '{stripped[:40]}' -> MAIN (default)")
    return Tier.MAIN


# ---------------------------------------------------------------------------
# Level-3 async routing (uses a FAST-tier LLM call to classify ambiguous text)
# ---------------------------------------------------------------------------


async def route_complexity_async(text: str) -> Tier:
    """Tier routing with LLM fallback.

    Levels 1 and 2 are identical to :func:`route_complexity`. If neither fires,
    a short FAST-tier classification call picks between FAST / MAIN / HEAVY.
    Results are LRU-cached by normalized text (max 100 entries). Any error in
    the classifier call falls back to MAIN.
    """
    stripped = text.strip()
    if not stripped:
        return Tier.FAST

    # Level 1
    if _GREETING_RE.match(stripped) or _SINGLE_WORD_RE.match(stripped):
        logger.debug(f"LLMRouter: '{stripped[:40]}' -> FAST (level 1)")
        return Tier.FAST

    # Level 2
    if _HEAVY_KEYWORDS_RE.search(stripped):
        logger.debug(f"LLMRouter: '{stripped[:40]}' -> HEAVY (level 2: heavy keyword)")
        return Tier.HEAVY
    if _MAIN_REALTIME_KEYWORDS_RE.search(stripped):
        logger.debug(f"LLMRouter: '{stripped[:40]}' -> MAIN (level 2: realtime keyword)")
        return Tier.MAIN

    # Level 3 — LLM classification (cache-guarded by lock so concurrent dupes collapse)
    cache_key = _cache_key(stripped)
    async with _classification_lock:
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug(f"LLMRouter: '{stripped[:40]}' -> {cached} (level 3, cached)")
            return cached

    tier = await _classify_via_llm(stripped)

    async with _classification_lock:
        _cache_put(cache_key, tier)
    logger.debug(f"LLMRouter: '{stripped[:40]}' -> {tier} (level 3)")
    return tier


async def _classify_via_llm(text: str) -> Tier:
    """Ask the FAST tier to classify ``text`` into a Tier. MAIN on any failure.

    We import ``llm_client`` lazily to avoid a circular import: llm_client may
    one day want to call back into the router for e.g. persona-pinned overrides.
    """
    from src.brain.llm_client import LLMError, complete

    prompt = _CLASSIFIER_PROMPT.format(text=text[:500])
    messages = [{"role": "user", "content": prompt}]

    try:
        pieces: list[str] = []
        async for chunk in complete(
            messages=messages,
            tier=Tier.FAST,
            stream=True,
            max_tokens=8,
            temperature=0.0,
        ):
            if chunk.content:
                pieces.append(chunk.content)
        raw = "".join(pieces).strip().lower()
    except LLMError as exc:
        logger.warning(f"LLMRouter: level-3 classifier failed ({exc.__class__.__name__}: {exc}) — defaulting to MAIN")
        return Tier.MAIN
    except Exception as exc:
        logger.warning(f"LLMRouter: level-3 classifier unexpected error ({exc!r}) — defaulting to MAIN")
        return Tier.MAIN

    # Strip any <think> tags emitted by reasoning models, take the first token.
    raw = re.sub(r"<think>[\s\S]*?</think>\s*", "", raw).strip()
    first = raw.split()[0].rstrip(".,!?:;") if raw.split() else ""
    if first in _VALID_TIERS:
        return Tier(first)

    logger.debug(f"LLMRouter: classifier returned unrecognised '{raw[:60]}' — defaulting to MAIN")
    return Tier.MAIN


# ---------------------------------------------------------------------------
# Tier -> concrete model-string resolution
# ---------------------------------------------------------------------------


def _read_llm_config() -> dict:
    """Load the LLM config section. Prefers the new ``get_config()`` API; falls back to YAML.

    The new ``src.shared.config.get_config`` returns a structured object; for v1.0
    we treat it as a plain dict if available, otherwise use the legacy YAML loader.
    """
    try:
        from src.shared.config import get_config  # type: ignore[attr-defined]
    except ImportError:
        get_config = None  # type: ignore[assignment]

    if get_config is not None:
        try:
            cfg = get_config()
            # Support both dict-shaped and attribute-shaped configs.
            if isinstance(cfg, dict):
                llm_cfg = cfg.get("llm", {})
            else:
                llm_cfg = getattr(cfg, "llm", {}) or {}
                if hasattr(llm_cfg, "model_dump"):
                    llm_cfg = llm_cfg.model_dump()
            if isinstance(llm_cfg, dict):
                return llm_cfg
        except Exception as exc:
            logger.debug(f"LLMRouter: get_config() unavailable ({exc!r}), falling back to YAML")

    from src.shared.config import get_yaml_config

    try:
        return get_yaml_config().get("llm", {}) or {}
    except Exception as exc:
        logger.warning(f"LLMRouter: YAML config unreadable ({exc!r}), using empty LLM config")
        return {}


def resolve_model(tier: Tier) -> str:
    """Return the concrete litellm model string for ``tier``.

    Resolution order:
      1. User's ``llm.tier_map[<tier>]`` in config, if set.
      2. Preset for ``llm.provider`` in config.
      3. DEFAULT_PROVIDER preset (Ollama) — last-resort so we never crash.

    Raises no exception by design; resolve_model must always return something
    callable, even if config is partially populated.
    """
    llm_cfg = _read_llm_config()
    tier_map = llm_cfg.get("tier_map") or {}

    override = tier_map.get(tier.value)
    if isinstance(override, str) and override.strip():
        return override.strip()

    provider = str(llm_cfg.get("provider") or DEFAULT_PROVIDER).lower()
    preset = TIER_PRESETS.get(provider) or TIER_PRESETS[DEFAULT_PROVIDER]
    model = preset[tier]
    logger.debug(f"LLMRouter: resolve_model({tier}) -> {model} (provider={provider}, preset)")
    return model


def resolve_provider(tier: Tier) -> str:
    """Return the provider name (e.g. ``anthropic``, ``ollama``) for the resolved model.

    Uses the litellm model-string convention of ``provider/model-name``. Falls back
    to the config's declared provider if the resolved model has no prefix (which
    shouldn't happen for real presets but keeps us defensive).
    """
    model = resolve_model(tier)
    if "/" in model:
        return model.split("/", 1)[0].lower()
    llm_cfg = _read_llm_config()
    return str(llm_cfg.get("provider") or DEFAULT_PROVIDER).lower()
