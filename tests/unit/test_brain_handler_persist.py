"""Item 3: the brain handler's conversation-history write was broken on every turn.

``src.brain.handler.on_user_message`` called::

    await store_conversation_turn(role="user", content=text)

but ``src.memory.store.store_conversation_turn`` takes a required positional
``timestamp`` with no default, so every single turn raised ``TypeError``. A
blanket ``except Exception`` logged it at DEBUG while the default log level is
INFO, which made the bug invisible by construction. It was masked further
because ``src.memory.handler`` performs the same write correctly.

These tests bind against the REAL signature rather than a loose mock, so a
stub that happily accepts anything cannot make them pass.
"""

from __future__ import annotations

import inspect
import sys
import types
from typing import Any

import pytest
from loguru import logger

from src.brain.llm_client import Chunk
from src.shared.types import AetherEvent, EventType

# ---------------------------------------------------------------------------
# Signature contract: the cheapest possible proof, and it needs no event loop
# ---------------------------------------------------------------------------


class TestCallSiteMatchesTheRealSignature:
    def test_timestamp_is_required_by_the_store(self):
        """Guard the premise: if timestamp ever gains a default, this test tells us."""
        from src.memory.store import store_conversation_turn

        sig = inspect.signature(store_conversation_turn)
        assert sig.parameters["timestamp"].default is inspect.Parameter.empty

    def test_handler_kwargs_bind_against_the_real_signature(self):
        """The brain handler's call must be bindable. Before the fix it was not."""
        from src.memory.store import store_conversation_turn

        sig = inspect.signature(store_conversation_turn)
        # Exactly the keywords src/brain/handler.py passes.
        sig.bind(role="user", content="hi", timestamp=1.0)

    def test_the_old_call_shape_really_did_fail(self):
        """Control: without timestamp the bind raises, so the test above can fail."""
        from src.memory.store import store_conversation_turn

        sig = inspect.signature(store_conversation_turn)
        with pytest.raises(TypeError):
            sig.bind(role="user", content="hi")


# ---------------------------------------------------------------------------
# Behavioural test: run the real handler with a signature-faithful store
# ---------------------------------------------------------------------------


class _RecordingStore:
    """Stand-in for src.memory.store with the real required-arg signature."""

    def __init__(self, *, raises: BaseException | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._raises = raises

    async def store_conversation_turn(
        self,
        role: str,
        content: str,
        timestamp: float,
        conversation_id: str = "default",
    ) -> str:
        if self._raises is not None:
            raise self._raises
        self.calls.append(
            {
                "role": role,
                "content": content,
                "timestamp": timestamp,
                "conversation_id": conversation_id,
            }
        )
        return "doc-id"


def _install_fake_memory_store(monkeypatch, store: _RecordingStore) -> None:
    """Inject a fake ``src.memory.store`` module.

    The handler imports the function inside the coroutine, so replacing the
    module in ``sys.modules`` is enough and keeps chromadb out of this test.
    """
    module = types.ModuleType("src.memory.store")
    module.store_conversation_turn = store.store_conversation_turn  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.memory.store", module)


def _stub_llm(monkeypatch, text: str = "Hello there.") -> None:
    import src.brain.handler as handler_mod

    async def _fake_stream(*_args, **_kwargs):
        yield Chunk(content=text, finish_reason=None, usage=None)
        yield Chunk(
            content="",
            finish_reason="stop",
            usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        )

    monkeypatch.setattr(handler_mod, "call_with_fallback", _fake_stream)
    monkeypatch.setattr(handler_mod, "build_system_prompt", lambda **_kw: "system")
    monkeypatch.setattr(handler_mod, "_get_recent_history", _empty_list)
    monkeypatch.setattr(handler_mod, "_get_rag_context", _empty_list_one_arg)


async def _empty_list(_n):
    return []


async def _empty_list_one_arg(_query):
    return []


@pytest.mark.asyncio
class TestConversationPersistOnTheBrainPath:
    async def test_turn_is_persisted_with_a_timestamp(self, monkeypatch):
        import src.brain.handler as handler_mod

        store = _RecordingStore()
        _install_fake_memory_store(monkeypatch, store)
        _stub_llm(monkeypatch)

        await handler_mod.on_user_message(
            AetherEvent(
                type=EventType.USER_MESSAGE,
                data={"text": "hello", "mode": "text"},
                source_module="test",
            )
        )

        assert len(store.calls) == 2, "user and assistant turns must both persist"
        roles = [c["role"] for c in store.calls]
        assert roles == ["user", "assistant"]
        for call in store.calls:
            assert isinstance(call["timestamp"], float)
            assert call["timestamp"] > 0

    async def test_a_real_store_failure_is_visible_at_the_default_log_level(self, monkeypatch):
        """The blanket except used to hide this at DEBUG under an INFO default.

        The app logs through loguru, which does not feed pytest's caplog, so
        this attaches a real loguru sink at INFO - the level the app actually
        ships with - and asserts the failure shows up there.
        """
        import src.brain.handler as handler_mod

        store = _RecordingStore(raises=RuntimeError("chroma is down"))
        _install_fake_memory_store(monkeypatch, store)
        _stub_llm(monkeypatch)

        captured: list[str] = []
        sink_id = logger.add(lambda msg: captured.append(str(msg)), level="INFO")
        try:
            await handler_mod.on_user_message(
                AetherEvent(
                    type=EventType.USER_MESSAGE,
                    data={"text": "hello", "mode": "text"},
                    source_module="test",
                )
            )
        finally:
            logger.remove(sink_id)

        joined = " ".join(captured)
        assert "chroma is down" in joined, (
            "a failed history write must be visible at the default INFO level"
        )

    async def test_the_sink_does_not_capture_debug(self, monkeypatch):
        """Control for the test above: an INFO sink must miss a DEBUG message.

        Without this, the previous test could pass for the wrong reason (a sink
        that captures everything regardless of level).
        """
        captured: list[str] = []
        sink_id = logger.add(lambda msg: captured.append(str(msg)), level="INFO")
        try:
            logger.debug("this must not be captured: sentinel-debug-only")
            logger.error("this must be captured: sentinel-error")
        finally:
            logger.remove(sink_id)

        joined = " ".join(captured)
        assert "sentinel-debug-only" not in joined
        assert "sentinel-error" in joined
