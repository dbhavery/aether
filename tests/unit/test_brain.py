"""Module 04 tests — verify brain routing and response generation."""

import pytest

from src.brain.persona import build_system_prompt
from src.brain.router import LLMTier, route
from src.shared.types import InteractionMode


class TestRouter:
    def test_greeting_routes_to_fast(self):
        assert route("hello") == LLMTier.FAST
        assert route("hi") == LLMTier.FAST
        assert route("thanks") == LLMTier.FAST

    def test_coding_routes_to_claude_heavy(self):
        assert route("write a Python function to sort a list") == LLMTier.CLAUDE_HEAVY
        assert route("debug this error") == LLMTier.CLAUDE_HEAVY

    def test_realtime_routes_to_gemini(self):
        assert route("what's the weather today") == LLMTier.GEMINI
        assert route("latest news") == LLMTier.GEMINI

    def test_general_routes_to_claude(self):
        assert route("tell me about yourself") == LLMTier.CLAUDE

    def test_force_tier_overrides(self):
        assert route("hello", force_tier=LLMTier.CLAUDE_HEAVY) == LLMTier.CLAUDE_HEAVY

    def test_summarize_routes_to_gemini_fast(self):
        assert route("summarize this document") == LLMTier.GEMINI_FAST

    def test_deep_research_routes_to_gemini_pro(self):
        assert route("research the impact of AI on healthcare") == LLMTier.GEMINI_PRO

    @pytest.mark.asyncio
    async def test_route_async_keyword_match(self):
        from src.brain.router import route_async

        tier = await route_async("hello")
        assert tier == LLMTier.FAST

    @pytest.mark.asyncio
    async def test_route_async_force_tier(self):
        from src.brain.router import route_async

        tier = await route_async("hello", force_tier=LLMTier.GEMINI_PRO)
        assert tier == LLMTier.GEMINI_PRO


class TestPersona:
    """Current v1.0 persona prompt is built from the active pack's system_prompt;
    when no pack is active (the case in these unit tests) a terse fallback is
    returned. The pre-v1.0 CORE-TRAITS/COMMUNICATION-STYLE/SILENT-PROTOCOL/
    flirtiness block no longer exists — those tests were deleted with the
    v13→v1.0 scope-cut. New persona-prompt behaviour is covered by the per-
    pack fixtures in tests/unit/test_personas.py."""

    def test_voice_mode_hint_differs_from_text(self):
        text_prompt = build_system_prompt(InteractionMode.TEXT)
        voice_prompt = build_system_prompt(InteractionMode.VOICE)
        assert "brief" in voice_prompt.lower()
        assert text_prompt != voice_prompt

    def test_voice_mode_no_markdown(self):
        prompt = build_system_prompt(InteractionMode.VOICE)
        assert "No markdown" in prompt

    def test_rag_context_injected(self):
        context = [{"content": "The user prefers dark mode", "metadata": {}, "relevance": 0.9}]
        prompt = build_system_prompt(InteractionMode.TEXT, rag_context=context)
        assert "The user prefers dark mode" in prompt
