"""Item 1: the per-stage latency instrument.

Before this module, ``time.perf_counter`` appeared zero times in the entire
repo, so no latency figure Aether had ever published could be regenerated.
These tests cover the instrument itself and then drive the real voice path end
to end with stubbed I/O, so the wiring is proven rather than assumed.

Every emission test has a control. A test that only asserts "nothing was
written when consent was declined" would also pass against an instrument that
never writes anything, so each one is paired with the consent-given case on the
same fixture.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest

from src.core import trace


@pytest.fixture(autouse=True)
def _isolated_trace_state(tmp_path, monkeypatch):
    """Point the trace log at a temp dir and clear in-memory state per test."""
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path))
    trace.reset_for_tests()
    yield
    trace.reset_for_tests()


def _grant_consent(monkeypatch, granted: bool) -> None:
    """Flip the single consent gate every emitter reads."""
    monkeypatch.setattr("src.core.trace.usage_counters_enabled", lambda: granted)
    monkeypatch.setattr("src.brain.cost.usage_counters_enabled", lambda: granted)


# ---------------------------------------------------------------------------
# The instrument itself
# ---------------------------------------------------------------------------


class TestPerfCounterIsActuallyUsed:
    def test_a_measured_stage_reflects_real_elapsed_time(self, monkeypatch):
        """Sleep a known duration and check the recorded figure brackets it."""
        _grant_consent(monkeypatch, True)
        turn = trace.start_turn("text")
        with trace.stage("stt"):
            import time as _time

            _time.sleep(0.05)
        recorded = turn.stages["stt"]
        assert 40.0 < recorded < 500.0, f"50ms sleep recorded as {recorded}ms"

    def test_an_unmeasured_stage_is_absent_not_zero(self, monkeypatch):
        """A stage that did not run must not appear as 0ms."""
        _grant_consent(monkeypatch, True)
        turn = trace.start_turn("text")
        with trace.stage("llm_complete"):
            pass
        assert "stt" not in turn.stages
        assert "wake_word" not in turn.stages

    def test_wake_word_and_vad_are_declared_uninstrumented(self):
        """They are reported with a reason, never as a measurement."""
        assert set(trace.UNINSTRUMENTED_STAGES) == {"wake_word", "vad"}
        for reason in trace.UNINSTRUMENTED_STAGES.values():
            assert reason.strip()

    def test_mark_keeps_the_first_occurrence(self, monkeypatch):
        """first_audio_ms must be the FIRST chunk out, not the last."""
        _grant_consent(monkeypatch, True)
        turn = trace.start_turn("voice")
        trace.mark("first_audio_ms")
        first = turn.marks["first_audio_ms"]
        import time as _time

        _time.sleep(0.02)
        trace.mark("first_audio_ms")
        assert turn.marks["first_audio_ms"] == first

    def test_stage_records_even_when_the_block_raises(self, monkeypatch):
        _grant_consent(monkeypatch, True)
        turn = trace.start_turn("text")
        with pytest.raises(RuntimeError), trace.stage("llm_complete"):
            raise RuntimeError("provider exploded")
        assert "llm_complete" in turn.stages

    def test_helpers_are_a_noop_with_no_turn_open(self):
        """Call sites carry no guards, so the helpers must tolerate no trace."""
        assert trace.current_turn() is None
        with trace.stage("stt"):
            pass
        trace.mark("first_audio_ms")
        trace.set_meta(anything=1)
        assert asyncio.run(trace.finish_turn()) is None


# ---------------------------------------------------------------------------
# Persistence and the consent gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPersistenceHonoursConsent:
    async def test_declined_consent_writes_nothing(self, monkeypatch):
        _grant_consent(monkeypatch, False)
        turn = trace.start_turn("voice")
        with trace.stage("stt"):
            pass
        assert await turn.finish() is None
        assert not trace.traces_path().exists(), "a declined user must leave no trace file"
        assert await trace.read_traces() == []

    async def test_granted_consent_writes_a_reproducible_record(self, monkeypatch):
        """Control for the test above: the same path DOES write when opted in."""
        _grant_consent(monkeypatch, True)
        turn = trace.start_turn("voice")
        with trace.stage("stt"):
            pass
        trace.mark("first_audio_ms")
        record = await turn.finish()

        assert record is not None
        assert trace.traces_path().exists()

        # Reproducible later, off disk, not only observed once in memory.
        on_disk = await trace.read_traces()
        assert len(on_disk) == 1
        assert on_disk[0]["turn_id"] == turn.turn_id
        assert on_disk[0]["stages_ms"]["stt"] >= 0.0
        assert on_disk[0]["first_audio_ms"] is not None
        assert on_disk[0]["source"] == "voice"
        # Every line is valid JSON on its own, so the log stays append-only safe.
        raw = trace.traces_path().read_text(encoding="utf-8").strip().splitlines()
        assert len(raw) == 1
        json.loads(raw[0])

    async def test_health_latency_block_is_empty_when_declined(self, monkeypatch):
        _grant_consent(monkeypatch, True)
        turn = trace.start_turn("voice")
        trace.mark("first_audio_ms")
        await turn.finish()

        _grant_consent(monkeypatch, False)
        summary = trace.get_latency_summary()
        assert summary["usage_counters_enabled"] is False
        assert "stages" not in summary, "declined consent must not expose recorded stages"

    async def test_health_latency_block_reports_real_stages_when_granted(self, monkeypatch):
        _grant_consent(monkeypatch, True)
        for _ in range(3):
            turn = trace.start_turn("voice")
            with trace.stage("stt"):
                pass
            trace.mark("first_audio_ms")
            await turn.finish()

        summary = trace.get_latency_summary()
        assert summary["usage_counters_enabled"] is True
        assert summary["turns_in_window"] == 3
        assert summary["stages"]["stt"]["count"] == 3
        assert summary["first_audio_ms"]["count"] == 3
        assert summary["last_turn"]["turn_id"] == turn.turn_id

    async def test_finish_is_idempotent(self, monkeypatch):
        """A double close must not double-count a turn in the rolling summary."""
        _grant_consent(monkeypatch, True)
        turn = trace.start_turn("text")
        assert await turn.finish() is not None
        assert await turn.finish() is None
        assert trace.get_latency_summary()["turns_in_window"] == 1


class TestPercentile:
    def test_p50_and_p95(self):
        values = [float(i) for i in range(1, 101)]
        assert trace._percentile(values, 50) == 50.0
        assert trace._percentile(values, 95) == 95.0

    def test_empty(self):
        assert trace._percentile([], 50) == 0.0

    def test_single_value(self):
        assert trace._percentile([7.5], 95) == 7.5


# ---------------------------------------------------------------------------
# The real voice path, with only the model calls stubbed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVoicePathIsInstrumentedEndToEnd:
    async def test_push_to_talk_release_produces_a_staged_trace(self, monkeypatch):
        """Drive VoicePipeline._on_speech_end through brain and TTS.

        Only the three model calls are stubbed (STT, LLM, TTS synth) plus audio
        playback. The event bus, the handlers, the ContextVar propagation and
        every timing call are the real ones, which is the point: this proves
        the trace survives EventBus task dispatch.
        """
        _grant_consent(monkeypatch, True)

        import src.brain.handler as brain_handler
        import src.voice.pipeline as pipeline_mod
        import src.voice.tts_handler as tts_mod
        from src.brain.llm_client import Chunk
        from src.core.events import event_bus
        from src.shared.types import AetherEvent, EventType

        # --- stub the three models and the speaker -------------------------
        async def _fake_transcribe(_audio, _rate):
            await asyncio.sleep(0.01)
            return "what is the low air warning pressure"

        async def _fake_stream(*_args, **_kwargs):
            await asyncio.sleep(0.01)
            yield Chunk(content="Fifty five psi.", finish_reason=None, usage=None)
            yield Chunk(
                content="",
                finish_reason="stop",
                usage={"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
                provider="ollama",
                model="ollama/qwen3.5:4b",
            )

        async def _fake_synthesize(_text):
            await asyncio.sleep(0.01)
            return np.zeros(1600, dtype=np.float32), 16000

        async def _fake_play(_audio, _rate):
            return None

        async def _no_history(_n):
            return []

        async def _no_rag(_q):
            return []

        monkeypatch.setattr(pipeline_mod, "transcribe", _fake_transcribe)
        monkeypatch.setattr(brain_handler, "call_with_fallback", _fake_stream)
        monkeypatch.setattr(brain_handler, "build_system_prompt", lambda **_kw: "system")
        monkeypatch.setattr(brain_handler, "_get_recent_history", _no_history)
        monkeypatch.setattr(brain_handler, "_get_rag_context", _no_rag)
        monkeypatch.setattr(brain_handler, "_persist_turn", _skip_persist)
        monkeypatch.setattr(tts_mod, "synthesize", _fake_synthesize)
        monkeypatch.setattr(tts_mod, "play_audio", _fake_play)

        # --- wire the real handlers onto the real bus ----------------------
        event_bus.subscribe(EventType.USER_MESSAGE, brain_handler.on_user_message)
        event_bus.subscribe(EventType.RESPONSE_TEXT_READY, tts_mod.on_response_text_ready)
        try:
            pipeline = pipeline_mod.VoicePipeline()
            pipeline._listening = True
            pipeline._buffer = [np.zeros(16000, dtype=np.float32)]
            pipeline._buffer_samples = 16000

            await pipeline._on_speech_end(
                AetherEvent(
                    type=EventType.USER_SPEECH_END,
                    data={},
                    source_module="test",
                )
            )
        finally:
            event_bus.unsubscribe(EventType.USER_MESSAGE, brain_handler.on_user_message)
            event_bus.unsubscribe(EventType.RESPONSE_TEXT_READY, tts_mod.on_response_text_ready)

        traces = await trace.read_traces()
        assert len(traces) == 1, "one push-to-talk release must yield exactly one trace"
        rec = traces[0]

        # Every stage on the live voice path recorded a real number.
        for stage_name in ("stt", "llm_complete", "tts_synth", "tts_publish_and_play"):
            assert stage_name in rec["stages_ms"], f"{stage_name} was not recorded"
            assert rec["stages_ms"][stage_name] > 0.0

        assert rec["marks_ms"]["llm_first_token"] > 0.0
        assert rec["first_audio_ms"] is not None
        assert rec["source"] == "voice"
        assert rec["meta"]["mode"] == "voice"
        # first audio must land inside the turn, and the turn total must be at
        # least as large as the slowest thing inside it.
        assert rec["first_audio_ms"] <= rec["turn_total_ms"]
        assert rec["turn_total_ms"] >= rec["stages_ms"]["stt"]
        # The stages that do not exist on this path are declared, not zeroed.
        assert set(rec["uninstrumented"]) == {"wake_word", "vad"}

    async def test_declined_consent_leaves_no_trace_on_the_voice_path(self, monkeypatch):
        """Same drive, consent off. Control for the test above."""
        _grant_consent(monkeypatch, False)

        import src.voice.pipeline as pipeline_mod
        from src.shared.types import AetherEvent, EventType

        async def _fake_transcribe(_audio, _rate):
            return "hello"

        monkeypatch.setattr(pipeline_mod, "transcribe", _fake_transcribe)

        pipeline = pipeline_mod.VoicePipeline()
        pipeline._listening = True
        pipeline._buffer = [np.zeros(16000, dtype=np.float32)]
        pipeline._buffer_samples = 16000
        await pipeline._on_speech_end(
            AetherEvent(type=EventType.USER_SPEECH_END, data={}, source_module="test")
        )

        assert not trace.traces_path().exists()


async def _skip_persist(*_args, **_kwargs) -> None:
    """Stand in for the memory write; chromadb is not what this test measures."""
    return None
