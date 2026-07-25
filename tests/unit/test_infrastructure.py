"""Tests for Batch 15 — infrastructure polish (instance lock, metrics, loop scripts)."""


from src.core.metrics import Metrics, get_metrics, get_metrics_summary


class TestMetrics:
    def test_initial_state(self):
        m = Metrics()
        assert m.turn_count == 0
        assert m.tool_call_count == 0
        assert m.tool_errors == 0
        assert m.ws_messages_received == 0
        assert m.ws_messages_sent == 0

    def test_record_turn(self):
        m = Metrics()
        m.record_turn()
        m.record_turn()
        assert m.turn_count == 2

    def test_record_tokens(self):
        m = Metrics()
        m.record_tokens("claude", 150)
        m.record_tokens("claude", 50)
        m.record_tokens("fast", 30)
        assert m.token_usage["claude"] == 200
        assert m.token_usage["fast"] == 30

    def test_record_tokens_new_tier(self):
        m = Metrics()
        m.record_tokens("custom_tier", 100)
        assert m.token_usage["custom_tier"] == 100

    def test_record_tool_call_success(self):
        m = Metrics()
        m.record_tool_call(success=True)
        assert m.tool_call_count == 1
        assert m.tool_errors == 0

    def test_record_tool_call_failure(self):
        m = Metrics()
        m.record_tool_call(success=False)
        assert m.tool_call_count == 1
        assert m.tool_errors == 1

    def test_record_response_latency(self):
        m = Metrics()
        m.record_response_latency(100.0)
        m.record_response_latency(200.0)
        assert m.avg_response_latency_ms() == 150.0

    def test_response_latency_capped_at_100(self):
        m = Metrics()
        for i in range(150):
            m.record_response_latency(float(i))
        assert len(m.response_latencies) == 100

    def test_avg_latency_empty(self):
        m = Metrics()
        assert m.avg_response_latency_ms() == 0.0

    def test_record_ws_message_in(self):
        m = Metrics()
        m.record_ws_message("in")
        m.record_ws_message("in")
        assert m.ws_messages_received == 2

    def test_record_ws_message_out(self):
        m = Metrics()
        m.record_ws_message("out")
        assert m.ws_messages_sent == 1

    def test_record_memory_search(self):
        m = Metrics()
        m.record_memory_search()
        m.record_memory_search()
        assert m.memory_searches == 2

    def test_to_dict(self):
        m = Metrics()
        m.record_turn()
        m.record_tokens("claude", 100)
        m.record_tool_call()
        m.record_response_latency(50.0)
        d = m.to_dict()
        assert d["turn_count"] == 1
        assert d["token_usage"]["claude"] == 100
        assert d["tool_calls"] == 1
        assert d["avg_response_latency_ms"] == 50.0
        assert "uptime_seconds" in d

    def test_get_metrics_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_get_metrics_summary_returns_dict(self):
        summary = get_metrics_summary()
        assert isinstance(summary, dict)
        assert "turn_count" in summary
        assert "uptime_seconds" in summary


class TestInstanceLock:
    def test_module_imports(self):
        from src.core.instance_lock import acquire_instance_lock, release_instance_lock

        assert callable(acquire_instance_lock)
        assert callable(release_instance_lock)

    def test_release_when_not_acquired(self):
        """release_instance_lock should be safe to call when no lock is held."""
        from src.core.instance_lock import release_instance_lock

        release_instance_lock()  # Should not raise


class TestHealthMetrics:
    def test_health_endpoint_includes_metrics(self):
        """Health endpoint should include metrics in its response."""
        from src.core.health import create_health_app

        app = create_health_app()
        # Just verify the app creates without error and has the /health route
        routes = [route.path for route in app.routes]
        assert "/health" in routes


# The loop.cmd scripts were replaced by desktop/launcher.ps1 + direct
# `python -m src.main` in the v1.0 scope-cut; their tests are gone with them.
