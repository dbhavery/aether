"""Tests for E2E integration audit fixes.

Covers: C1/C3 (EventBus wiring), C4 (agent task notifications), H1 (ChromaDB shutdown),
H5 (Ollama timeout), H6 (duplicate TOOL_REGISTRY), M1 (approval IDs), M2 (signal handler),
M3 (error message filtering), M4 (avatar speaking reset), M5 (embedding model check),
M6 (daily interview busy detection), M7 (ingest extensions), M8 (device token setting),
M9 (CLAUDE_HEAVY fallback), M10 (proactive message storage).
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# C1/C3: Server subscribes to TRANSCRIPT_READY and SPEAKER_VERIFIED
# ---------------------------------------------------------------------------


class TestServerEventSubscriptions:
    """Verify server subscribes to transcript and speaker events."""

    def test_server_has_transcript_handler(self):
        from src.core.server import _on_transcript_ready

        assert asyncio.iscoroutinefunction(_on_transcript_ready)

    def test_server_has_speaker_verified_handler(self):
        from src.core.server import _on_speaker_verified

        assert asyncio.iscoroutinefunction(_on_speaker_verified)

    def test_start_websocket_server_subscribes_transcript(self):
        source = inspect.getsource(
            __import__("src.core.server", fromlist=["start_websocket_server"]).start_websocket_server
        )
        assert "TRANSCRIPT_READY" in source
        assert "SPEAKER_VERIFIED" in source


# ---------------------------------------------------------------------------
# C4: Notifications subscribe to AGENT_TASK_COMPLETE
# ---------------------------------------------------------------------------


class TestAgentTaskNotification:
    """Verify notification handler handles agent task completion."""

    def test_notification_handler_has_agent_complete(self):
        from src.notifications.handler import on_agent_task_complete

        assert asyncio.iscoroutinefunction(on_agent_task_complete)

    def test_register_subscribes_agent_complete(self):
        source = inspect.getsource(
            __import__(
                "src.notifications.handler", fromlist=["register_notification_handlers"]
            ).register_notification_handlers
        )
        assert "AGENT_TASK_COMPLETE" in source


# ---------------------------------------------------------------------------
# H1: ChromaDB shutdown cleanup
# ---------------------------------------------------------------------------


class TestChromaDBShutdown:
    """Verify ChromaDB cleanup in shutdown sequence."""

    def test_shutdown_includes_chromadb_cleanup(self):
        from src.core.shutdown import _shutdown_sequence

        source = inspect.getsource(_shutdown_sequence)
        assert "chroma_client" in source or "ChromaDB" in source


# ---------------------------------------------------------------------------
# H5: Ollama timeout from config
# ---------------------------------------------------------------------------


class TestOllamaTimeout:
    """Verify Ollama uses config-based timeout instead of hardcoded 60s."""

    def test_call_ollama_uses_get_timeout(self):
        from src.brain.clients import call_ollama

        source = inspect.getsource(call_ollama)
        assert "_get_timeout" in source
        assert "total=60" not in source


# ---------------------------------------------------------------------------
# H6: No duplicate TOOL_REGISTRY
# ---------------------------------------------------------------------------


class TestToolRegistryDedup:
    """Verify handler imports TOOL_REGISTRY from dispatcher."""

    def test_handler_imports_from_dispatcher(self):
        source = inspect.getsource(__import__("src.tools.handler", fromlist=["handler"]))
        assert "from src.tools.dispatcher import TOOL_REGISTRY" in source

    def test_registry_is_same_object(self):
        from src.tools.dispatcher import TOOL_REGISTRY as dispatcher_reg
        from src.tools.handler import TOOL_REGISTRY as handler_reg

        assert handler_reg is dispatcher_reg


# ---------------------------------------------------------------------------
# M1: Approval IDs use uuid4
# ---------------------------------------------------------------------------


class TestApprovalIDs:
    """Verify approval IDs use uuid4 instead of id()."""

    def test_no_id_call_in_approval(self):
        from src.tools.approval_gate import request_approval

        source = inspect.getsource(request_approval)
        assert "id(description)" not in source
        assert "uuid" in source

    def test_uuid_imported(self):
        import src.tools.approval_gate as gate

        assert hasattr(gate, "uuid")


# ---------------------------------------------------------------------------
# M2: Windows signal handler thread safety
# ---------------------------------------------------------------------------


class TestSignalHandlerSafety:
    """Verify Windows signal handler uses call_soon_threadsafe."""

    def test_shutdown_uses_call_soon_threadsafe(self):
        from src.core.shutdown import register_shutdown_handlers

        source = inspect.getsource(register_shutdown_handlers)
        assert "call_soon_threadsafe" in source


# ---------------------------------------------------------------------------
# M3: Error messages filtered from memory + M10: proactive stored
# ---------------------------------------------------------------------------


class TestMemoryFiltering:
    """Verify error messages are filtered and proactive messages are stored."""

    def test_error_phrases_defined(self):
        from src.memory.handler import _ERROR_PHRASES

        assert len(_ERROR_PHRASES) >= 2

    @pytest.mark.asyncio
    async def test_error_response_not_stored(self):
        from src.memory.handler import on_response_ready
        from src.shared.types import EventType, AetherEvent

        event = AetherEvent(
            type=EventType.RESPONSE_TEXT_READY,
            data={"text": "Something went wrong on my end. Give me a moment.", "is_interim": False},
        )
        with patch("src.memory.handler.store_conversation_turn", new_callable=AsyncMock) as mock_store:
            await on_response_ready(event)
            mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_response_stored(self):
        from src.memory.handler import on_response_ready
        from src.shared.types import EventType, AetherEvent

        event = AetherEvent(
            type=EventType.RESPONSE_TEXT_READY,
            data={"text": "Hello User, how can I help?", "is_interim": False},
        )
        with patch("src.memory.handler.store_conversation_turn", new_callable=AsyncMock) as mock_store:
            await on_response_ready(event)
            mock_store.assert_called_once()

    def test_proactive_handler_exists(self):
        from src.memory.handler import on_proactive_message

        assert asyncio.iscoroutinefunction(on_proactive_message)

    def test_register_subscribes_proactive(self):
        source = inspect.getsource(
            __import__("src.memory.handler", fromlist=["register_memory_handlers"]).register_memory_handlers
        )
        assert "PROACTIVE_MESSAGE" in source


# ---------------------------------------------------------------------------
# M4: Avatar speaking state reset
# ---------------------------------------------------------------------------


class TestAvatarSpeakingReset:
    """Verify avatar handler resets speaking state."""

    def test_avatar_handler_has_user_message_handler(self):
        from src.avatar.handler import on_user_message

        assert asyncio.iscoroutinefunction(on_user_message)

    def test_avatar_registers_user_message(self):
        source = inspect.getsource(
            __import__("src.avatar.handler", fromlist=["register_avatar_handlers"]).register_avatar_handlers
        )
        assert "USER_MESSAGE" in source


# ---------------------------------------------------------------------------
# M5: ensure_embedding_model at startup
# ---------------------------------------------------------------------------


class TestEmbeddingModelCheck:
    """Verify ensure_embedding_model is called during startup."""

    def test_startup_checks_embedding_model(self):
        from src.core.startup import startup

        source = inspect.getsource(startup)
        assert "ensure_embedding_model" in source


# ---------------------------------------------------------------------------
# M6: Daily interview busy detection
# ---------------------------------------------------------------------------


class TestDailyInterviewBusy:
    """Verify daily interview checks busy detector."""

    def test_interview_checks_availability(self):
        from src.persona.daily_interview import start_interview_session

        source = inspect.getsource(start_interview_session)
        assert "get_busy_detector" in source
        assert "sleeping" in source or "likely_busy" in source


# ---------------------------------------------------------------------------
# M7: Ingest extensions synced
# ---------------------------------------------------------------------------


class TestIngestExtensions:
    """Verify ingest extension list matches classify_media_type."""

    def test_classify_extensions_are_ingested(self):
        """All extensions recognized by classify_media_type should be in ingest list."""

        source = inspect.getsource(
            __import__("src.data_server.app", fromlist=["_ingest_folder_task"])._ingest_folder_task
        )
        # Check key extensions that were previously missing
        for ext in [".svg", ".ico", ".jfif", ".ts", ".vob", ".mts", ".wma", ".pptx", ".xlsx", ".csv"]:
            assert f'"{ext}"' in source, f"Extension {ext} missing from ingest list"


# ---------------------------------------------------------------------------
# M8: android_device_token in settings
# ---------------------------------------------------------------------------


class TestDeviceTokenSetting:
    """Verify android_device_token is a proper settings field."""

    def test_settings_has_device_token(self):
        from src.shared.config import AetherSettings

        fields = AetherSettings.model_fields
        assert "android_device_token" in fields


# ---------------------------------------------------------------------------
# M9: CLAUDE_HEAVY fallback to sonnet
# ---------------------------------------------------------------------------


class TestClaudeHeavyFallback:
    """Verify CLAUDE_HEAVY falls back to regular CLAUDE before GEMINI."""

    def test_fallback_allows_claude_from_heavy(self):
        from src.brain.handler import _call_with_fallback

        source = inspect.getsource(_call_with_fallback)
        # The old code had: tier not in (LLMTier.CLAUDE, LLMTier.CLAUDE_HEAVY)
        # The fix should be: tier != LLMTier.CLAUDE
        assert "tier != LLMTier.CLAUDE:" in source
        assert "tier not in (LLMTier.CLAUDE, LLMTier.CLAUDE_HEAVY)" not in source
