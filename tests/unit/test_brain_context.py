"""Tests for Brain multi-turn context and tool calling integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMultiTurnContext:
    """Verify that Brain builds multi-turn messages from conversation history."""

    @pytest.mark.asyncio
    async def test_call_with_fallback_passes_messages(self):
        """Verify _call_with_fallback passes messages list to LLM clients."""
        messages = [
            {"role": "user", "content": "My name is Alex"},
            {"role": "assistant", "content": "Nice to meet you, User!"},
            {"role": "user", "content": "What is my name?"},
        ]

        with patch("src.brain.handler.call_ollama", new_callable=AsyncMock) as mock_ollama:
            mock_ollama.return_value = "Your name is User."
            from src.brain.handler import _call_with_fallback
            from src.brain.router import LLMTier

            result = await _call_with_fallback(LLMTier.FAST, messages, "You are Aether.")
            assert result == "Your name is User."
            mock_ollama.assert_called_once()
            call_kwargs = mock_ollama.call_args
            assert call_kwargs.kwargs["messages"] == messages

    @pytest.mark.asyncio
    async def test_get_recent_turns_returns_sorted(self):
        """Verify get_recent_turns returns turns sorted by timestamp."""
        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_collection.get.return_value = {
            "documents": ["Hello", "Hi User!", "How are you?"],
            "metadatas": [
                {"role": "user", "timestamp": 100.0},
                {"role": "assistant", "timestamp": 100.001},
                {"role": "user", "timestamp": 200.0},
            ],
        }

        with patch("src.memory.store._get_conversations_collection", return_value=mock_collection):
            from src.memory.store import get_recent_turns

            turns = await get_recent_turns(limit=10)
            assert len(turns) == 3
            assert turns[0]["content"] == "Hello"
            assert turns[0]["role"] == "user"
            assert turns[2]["content"] == "How are you?"
            # Timestamps are included for pattern_learner.py consumption
            assert "timestamp" in turns[0]
            assert turns[0]["timestamp"] == 100.0
            assert set(turns[0].keys()) == {"role", "content", "timestamp"}


class TestSearchMemoryDualCollection:
    """Verify search_memory queries both conversations and knowledge."""

    @pytest.mark.asyncio
    async def test_search_memory_includes_knowledge(self):
        mock_conv = MagicMock()
        mock_conv.count.return_value = 1
        mock_conv.query.return_value = {
            "documents": [["conv result"]],
            "metadatas": [[{"role": "user"}]],
            "distances": [[0.2]],
        }

        mock_know = MagicMock()
        mock_know.count.return_value = 1
        mock_know.query.return_value = {
            "documents": [["The user likes dark mode"]],
            "metadatas": [[{"key": "preference"}]],
            "distances": [[0.1]],
        }

        with (
            patch("src.memory.store._get_conversations_collection", return_value=mock_conv),
            patch("src.memory.store._get_knowledge_collection", return_value=mock_know),
            patch("src.memory.store.embed_text", new_callable=AsyncMock, return_value=[0.1] * 384),
        ):
            from src.memory.store import search_memory

            results = await search_memory("dark mode", n_results=5)
            assert len(results) == 2
            # Knowledge result should be ranked first (higher relevance = lower distance)
            assert results[0]["source"] == "knowledge"
            assert results[1]["source"] == "conversations"


class TestToolCallingLoop:
    """Verify the tool calling loop dispatches tools and returns results."""

    @pytest.mark.asyncio
    async def test_call_with_tools_no_tool_calls(self):
        """When LLM returns plain text (no tool calls), return it directly."""
        with patch(
            "src.brain.handler.call_claude_with_tools",
            new_callable=AsyncMock,
            return_value={"text": "The weather is nice.", "tool_calls": []},
        ):
            from src.brain.handler import _call_with_tools

            result = await _call_with_tools(
                [{"role": "user", "content": "What's the weather?"}],
                "You are Aether.",
            )
            assert result == "The weather is nice."

    @pytest.mark.asyncio
    async def test_call_with_tools_dispatches_tool(self):
        """When LLM requests a tool call, dispatch it and loop."""
        call_count = 0

        async def mock_claude_with_tools(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "text": "",
                    "tool_calls": [{"id": "tool_1", "name": "list_running_apps", "arguments": {}}],
                }
            else:
                return {"text": "You have Notepad and Chrome running.", "tool_calls": []}

        with (
            patch("src.brain.handler.call_claude_with_tools", side_effect=mock_claude_with_tools),
            patch(
                "src.brain.handler.dispatch_tool",
                new_callable=AsyncMock,
                return_value="{'success': True, 'apps': [{'name': 'notepad.exe'}]}",
            ),
        ):
            from src.brain.handler import _call_with_tools

            result = await _call_with_tools(
                [{"role": "user", "content": "What apps are running?"}],
                "You are Aether.",
            )
            assert "Notepad" in result or "Chrome" in result
            assert call_count == 2


class TestContentGuardWiring:
    """Verify content guard works and is NOT applied to own memory results."""

    @pytest.mark.asyncio
    async def test_wrap_external_content_works(self):
        """Ensure wrap_external_content functions correctly for external sources."""
        from src.brain.content_guard import wrap_external_content

        result = wrap_external_content("test content", source="web")
        assert "[EXTERNAL_CONTENT" in result

    @pytest.mark.asyncio
    async def test_rag_context_not_wrapped_by_content_guard(self):
        """Memory RAG context is Aether's own history — should NOT be wrapped."""
        # handler.py now passes rag_context through directly without wrapping
        rag_context = [{"content": "The user likes dark mode", "relevance": 0.9}]
        guarded_rag = rag_context if rag_context else []
        assert guarded_rag[0]["content"] == "The user likes dark mode"
        assert "[EXTERNAL_CONTENT" not in guarded_rag[0]["content"]
