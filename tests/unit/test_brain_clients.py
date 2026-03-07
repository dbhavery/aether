"""Test LLM client routing and error handling. All LLM calls mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBrainClientImports:
    """Verify brain client modules import cleanly."""

    def test_clients_module_imports(self):
        from src.brain import clients

        assert hasattr(clients, "call_ollama")
        assert hasattr(clients, "call_claude")
        assert hasattr(clients, "call_gemini")
        assert hasattr(clients, "call_claude_with_tools")

    def test_handler_module_imports(self):
        from src.brain import handler

        assert hasattr(handler, "on_user_message")
        assert hasattr(handler, "register_brain_handlers")

    def test_router_module_imports(self):
        from src.brain import router

        assert hasattr(router, "route")
        assert hasattr(router, "LLMTier")


class TestEnsureMessages:
    """Test the _ensure_messages helper."""

    def test_prompt_wraps_to_messages(self):
        from src.brain.clients import _ensure_messages

        result = _ensure_messages("hello", None)
        assert result == [{"role": "user", "content": "hello"}]

    def test_messages_passthrough(self):
        from src.brain.clients import _ensure_messages

        msgs = [{"role": "user", "content": "hi"}]
        result = _ensure_messages(None, msgs)
        assert result is msgs

    def test_neither_raises(self):
        from src.brain.clients import _ensure_messages

        with pytest.raises(ValueError, match="Either prompt or messages"):
            _ensure_messages(None, None)


class TestCallOllama:
    """Test Ollama client with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_ollama_returns_text(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"message": {"content": "Hello from Ollama"}})

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session_ctx)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.post = MagicMock(return_value=mock_post_ctx)

        with (
            patch("aiohttp.ClientSession", return_value=mock_session_ctx),
            patch("src.brain.clients.get_settings") as mock_settings,
            patch("src.brain.clients.get_yaml_config") as mock_yaml,
        ):
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_yaml.return_value = {"llm": {"fast_model": "qwen2.5:7b", "fast_max_tokens": 2048}}

            from src.brain.clients import call_ollama

            result = await call_ollama(prompt="test")
            assert result == "Hello from Ollama"


class TestCallWithFallback:
    """Test the fallback chain in the brain handler."""

    @pytest.mark.asyncio
    async def test_fallback_chain_tries_alternatives(self):
        with (
            patch(
                "src.brain.handler.call_claude",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Claude down"),
            ),
            patch(
                "src.brain.handler.call_gemini",
                new_callable=AsyncMock,
                return_value="Gemini fallback response",
            ),
        ):
            from src.brain.handler import _call_with_fallback
            from src.brain.router import LLMTier

            result = await _call_with_fallback(
                LLMTier.CLAUDE,
                [{"role": "user", "content": "hi"}],
                "system prompt",
            )
            assert result == "Gemini fallback response"

    @pytest.mark.asyncio
    async def test_fast_tier_calls_ollama(self):
        with patch(
            "src.brain.handler.call_ollama",
            new_callable=AsyncMock,
            return_value="Local response",
        ):
            from src.brain.handler import _call_with_fallback
            from src.brain.router import LLMTier

            result = await _call_with_fallback(
                LLMTier.FAST,
                [{"role": "user", "content": "hi"}],
                "system prompt",
            )
            assert result == "Local response"


class TestRouter:
    """Test the LLM routing logic."""

    def test_route_returns_valid_tier(self):
        from src.brain.router import LLMTier, route

        tier = route("What time is it?")
        assert isinstance(tier, str)
        valid_tiers = {
            LLMTier.FAST,
            LLMTier.CLAUDE,
            LLMTier.CLAUDE_HEAVY,
            LLMTier.GEMINI,
            LLMTier.GEMINI_FAST,
            LLMTier.GEMINI_PRO,
        }
        assert tier in valid_tiers
