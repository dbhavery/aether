"""Item 2: the cost accountant and metrics recorders are reachable from production.

`src/brain/cost.py` (376 lines: litellm pricing, JSONL persistence, atomic
writes, daily budgets) and `src/core/metrics.py` both existed, were both tested,
and were both dead code. `track_usage` had zero call sites. The metrics
recorders were only ever reached from `tests/unit/test_infrastructure.py`, which
is why `/health` served a permanently all-zero metrics block.

Token usage was already being parsed off every provider response in
`src/brain/llm_client._normalise_usage` and then thrown away by the brain
handler, which read only `chunk.content`.

These tests assert the wiring, not the modules. The modules already had tests.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from src.brain.llm_client import Chunk
from src.shared.types import AetherEvent, EventType


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path))
    from src.core import metrics as metrics_mod
    from src.core import trace as trace_mod

    # Fresh singleton per test: the metrics counters are module-level.
    monkeypatch.setattr(metrics_mod, "_metrics", None)
    trace_mod.reset_for_tests()
    yield
    trace_mod.reset_for_tests()


def _grant_consent(monkeypatch, granted: bool) -> None:
    monkeypatch.setattr("src.brain.cost.usage_counters_enabled", lambda: granted)
    monkeypatch.setattr("src.core.trace.usage_counters_enabled", lambda: granted)
    monkeypatch.setattr("src.shared.config.usage_counters_enabled", lambda: granted)


def _stub_brain(monkeypatch, *, usage: dict[str, int] | None, provider: str | None, model: str | None):
    import src.brain.handler as handler_mod

    async def _fake_stream(*_args, **_kwargs):
        yield Chunk(content="Fifty five psi.", finish_reason=None, usage=None)
        yield Chunk(
            content="",
            finish_reason="stop",
            usage=usage,
            provider=provider,
            model=model,
        )

    async def _no_history(_n):
        return []

    async def _no_rag(_q):
        return []

    async def _no_persist(*_a, **_kw):
        return None

    monkeypatch.setattr(handler_mod, "call_with_fallback", _fake_stream)
    monkeypatch.setattr(handler_mod, "build_system_prompt", lambda **_kw: "system")
    monkeypatch.setattr(handler_mod, "_get_recent_history", _no_history)
    monkeypatch.setattr(handler_mod, "_get_rag_context", _no_rag)
    monkeypatch.setattr(handler_mod, "_persist_turn", _no_persist)
    # Keep chromadb out of this test; the persist path has its own tests.
    monkeypatch.setitem(sys.modules, "src.memory.store", types.ModuleType("src.memory.store"))
    return handler_mod


async def _run_one_turn(handler_mod, text: str = "hello") -> None:
    await handler_mod.on_user_message(
        AetherEvent(
            type=EventType.USER_MESSAGE,
            data={"text": text, "mode": "text"},
            source_module="test",
        )
    )


# ---------------------------------------------------------------------------
# track_usage now has a production call site
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTrackUsageIsCalledFromTheBrain:
    async def test_a_turn_writes_a_usage_record(self, monkeypatch, tmp_path):
        _grant_consent(monkeypatch, True)
        handler_mod = _stub_brain(
            monkeypatch,
            usage={"prompt_tokens": 215, "completion_tokens": 2287, "total_tokens": 2502},
            provider="ollama",
            model="ollama/qwen3.5:4b",
        )

        usage_log = tmp_path / "usage.jsonl"
        assert not usage_log.exists(), "premise: nothing recorded before the turn"

        await _run_one_turn(handler_mod)

        assert usage_log.exists(), "track_usage still has no reachable call site"
        record = json.loads(usage_log.read_text(encoding="utf-8").strip())
        assert record["provider"] == "ollama"
        assert record["model"] == "ollama/qwen3.5:4b"
        assert record["input_tokens"] == 215
        assert record["output_tokens"] == 2287
        assert "cost_usd" in record

    async def test_cost_is_attributed_to_the_provider_that_answered(self, monkeypatch, tmp_path):
        """The fallback cascade can land on a different tier than was requested.

        Attribution comes off the chunk, so a turn that fell back to another
        provider is billed to that provider and not to the requested one.
        """
        _grant_consent(monkeypatch, True)
        handler_mod = _stub_brain(
            monkeypatch,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            provider="groq",
            model="groq/llama-3.3-70b-versatile",
        )
        await _run_one_turn(handler_mod)
        record = json.loads((tmp_path / "usage.jsonl").read_text(encoding="utf-8").strip())
        assert record["provider"] == "groq"

    async def test_no_record_when_the_provider_reported_no_usage(self, monkeypatch, tmp_path):
        """A guessed token count is worse than no record. Control for the tests above."""
        _grant_consent(monkeypatch, True)
        handler_mod = _stub_brain(monkeypatch, usage=None, provider="ollama", model="ollama/qwen3.5:4b")
        await _run_one_turn(handler_mod)
        assert not (tmp_path / "usage.jsonl").exists()

    async def test_no_record_without_a_provider_identity(self, monkeypatch, tmp_path):
        """Usage with no provider must not be filed under a guess."""
        _grant_consent(monkeypatch, True)
        handler_mod = _stub_brain(
            monkeypatch,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            provider=None,
            model=None,
        )
        await _run_one_turn(handler_mod)
        assert not (tmp_path / "usage.jsonl").exists()

    async def test_declined_consent_records_nothing(self, monkeypatch, tmp_path):
        _grant_consent(monkeypatch, False)
        handler_mod = _stub_brain(
            monkeypatch,
            usage={"prompt_tokens": 215, "completion_tokens": 2287, "total_tokens": 2502},
            provider="ollama",
            model="ollama/qwen3.5:4b",
        )
        await _run_one_turn(handler_mod)
        assert not (tmp_path / "usage.jsonl").exists()


# ---------------------------------------------------------------------------
# The metrics recorders now run in production
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMetricsAreRecordedByATurn:
    async def test_metrics_move_off_zero(self, monkeypatch):
        from src.core.metrics import get_metrics_summary

        _grant_consent(monkeypatch, True)

        before = get_metrics_summary()
        assert before["turn_count"] == 0
        assert before["avg_response_latency_ms"] == 0.0
        assert sum(before["token_usage"].values()) == 0

        handler_mod = _stub_brain(
            monkeypatch,
            usage={"prompt_tokens": 215, "completion_tokens": 2287, "total_tokens": 2502},
            provider="ollama",
            model="ollama/qwen3.5:4b",
        )
        await _run_one_turn(handler_mod)

        after = get_metrics_summary()
        assert after["turn_count"] == 1, "record_turn is still unreachable from production"
        assert after["avg_response_latency_ms"] > 0.0
        assert sum(after["token_usage"].values()) == 2502

    async def test_two_turns_accumulate(self, monkeypatch):
        from src.core.metrics import get_metrics_summary

        _grant_consent(monkeypatch, True)
        handler_mod = _stub_brain(
            monkeypatch,
            usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            provider="ollama",
            model="ollama/qwen3.5:4b",
        )
        await _run_one_turn(handler_mod)
        await _run_one_turn(handler_mod, "hello again")
        summary = get_metrics_summary()
        assert summary["turn_count"] == 2
        assert sum(summary["token_usage"].values()) == 6


# ---------------------------------------------------------------------------
# /health serves real numbers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHealthServesRealNumbers:
    async def _get_health(self):
        from fastapi.testclient import TestClient

        from src.core.health import create_health_app

        client = TestClient(create_health_app())
        response = client.get("/health")
        assert response.status_code == 200
        return response.json()

    async def test_health_reports_the_turn_and_its_cost(self, monkeypatch):
        _grant_consent(monkeypatch, True)
        handler_mod = _stub_brain(
            monkeypatch,
            usage={"prompt_tokens": 215, "completion_tokens": 2287, "total_tokens": 2502},
            provider="ollama",
            model="ollama/qwen3.5:4b",
        )

        zeroed = await self._get_health()
        assert zeroed["metrics"]["turn_count"] == 0, "premise: /health starts at zero"

        await _run_one_turn(handler_mod)

        live = await self._get_health()
        assert live["metrics"]["turn_count"] == 1
        assert live["metrics"]["avg_response_latency_ms"] > 0.0
        assert live["cost"]["usage_counters_enabled"] is True
        assert live["cost"]["providers"]["ollama"]["calls"] == 1
        assert live["cost"]["providers"]["ollama"]["input_tokens"] == 215
        assert live["latency"]["usage_counters_enabled"] is True
        assert live["latency"]["turns_in_window"] == 1
        assert live["latency"]["stages"]["llm_complete"]["count"] == 1

    async def test_health_declares_a_declined_gate_rather_than_serving_zeroes(self, monkeypatch):
        _grant_consent(monkeypatch, False)
        health = await self._get_health()
        assert health["cost"]["usage_counters_enabled"] is False
        assert "providers" not in health["cost"]
        assert health["latency"]["usage_counters_enabled"] is False


# ---------------------------------------------------------------------------
# The dollar figure comes from litellm's real price table
# ---------------------------------------------------------------------------


class TestCostIsARealDollarFigure:
    def test_a_local_model_is_free(self):
        from src.brain.cost import _estimate_cost_usd

        assert _estimate_cost_usd("ollama", "ollama/qwen3.5:4b", 215, 2287) == 0.0

    def test_a_cloud_model_prices_above_zero_from_the_real_table(self):
        """Control for the test above: the same function must NOT return 0 for a
        priced model, or "free" would be meaningless.

        litellm's cost_per_token reads a bundled price table, so this needs no
        network call and spends nothing.
        """
        pytest.importorskip("litellm", reason="litellm is in requirements.txt but not installed here")
        from src.brain.cost import _estimate_cost_usd

        cost = _estimate_cost_usd("openai", "gpt-4o", 1_000_000, 1_000_000)
        assert cost > 0.0, "a metered model must produce a real dollar figure"
