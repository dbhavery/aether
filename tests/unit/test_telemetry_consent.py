"""Item 0 — the telemetry consent gate must actually be readable and honoured.

The setup wizard collects ``telemetry.usage_counters`` (frontend StepTerms)
and ``src.onboarding.finalizer`` writes it into config.yaml, but before this
change ``TelemetrySettings`` had no field for it, so the value round-tripped
into the file and was then invisible to every consumer. Collecting counters a
user declined is a privacy defect, so the gate is tested before anything else
is allowed to emit.

Control cases are included deliberately: a test that only ever asserts
"emission is blocked" would also pass if emission were broken outright.
"""

from __future__ import annotations

import pytest

from src.shared.config import TelemetrySettings, usage_counters_enabled


class TestTelemetrySettingsField:
    def test_usage_counters_field_exists(self):
        """The wizard's third telemetry switch must be readable back off config."""
        assert hasattr(TelemetrySettings(), "usage_counters")

    def test_usage_counters_defaults_to_declined(self):
        """Absent setting means the more private choice."""
        assert TelemetrySettings().usage_counters is False

    def test_usage_counters_round_trips(self):
        """A value written by the finalizer must survive validation."""
        parsed = TelemetrySettings.model_validate(
            {"enabled": True, "crash_reports": False, "usage_counters": True}
        )
        assert parsed.usage_counters is True


class TestUsageCountersGate:
    """``usage_counters_enabled()`` is the single choke point every emitter reads."""

    @pytest.mark.parametrize(
        ("enabled", "usage_counters", "expected"),
        [
            (True, True, True),  # control: consent given, gate must OPEN
            (True, False, False),
            (False, True, False),  # master switch off overrides the sub-flag
            (False, False, False),
        ],
    )
    def test_gate_requires_both_flags(self, monkeypatch, enabled, usage_counters, expected):
        monkeypatch.setattr(
            "src.shared.config.get_config",
            lambda: _FakeConfig(enabled=enabled, usage_counters=usage_counters),
        )
        assert usage_counters_enabled() is expected

    def test_gate_closed_when_config_unreadable(self, monkeypatch):
        """A broken or missing config must not be read as consent."""

        def _boom():
            raise OSError("config.yaml is gone")

        monkeypatch.setattr("src.shared.config.get_config", _boom)
        assert usage_counters_enabled() is False

    def test_gate_closed_when_telemetry_block_missing(self, monkeypatch):
        """An older config with no telemetry block at all means declined."""
        monkeypatch.setattr("src.shared.config.get_config", lambda: object())
        assert usage_counters_enabled() is False


class TestConsentRoundTripsThroughTheRealConfigFile:
    """The defect was a value that survived to disk and then vanished on read."""

    def _write_config(self, tmp_path, *, enabled: bool, usage_counters: bool):
        import src.shared.config as cfg_mod

        path = tmp_path / "config.yaml"
        path.write_text(
            "aether:\n"
            "  version: 1\n"
            '  user_installation_id: "11111111-2222-3333-4444-555555555555"\n'
            "  telemetry:\n"
            f"    enabled: {str(enabled).lower()}\n"
            "    crash_reports: false\n"
            f"    usage_counters: {str(usage_counters).lower()}\n",
            encoding="utf-8",
        )
        return path

    def _load(self, monkeypatch, path):
        import src.shared.config as cfg_mod

        monkeypatch.setattr(cfg_mod, "get_config_path", lambda: path)
        monkeypatch.setattr(cfg_mod, "_config_cache", None)
        monkeypatch.setattr(cfg_mod, "_raw_cache", None)
        monkeypatch.setattr(cfg_mod, "_raw_cache_path", None)
        return cfg_mod

    def test_opt_in_survives_a_real_load(self, tmp_path, monkeypatch):
        path = self._write_config(tmp_path, enabled=True, usage_counters=True)
        cfg_mod = self._load(monkeypatch, path)
        assert cfg_mod.get_config().aether.telemetry.usage_counters is True
        assert cfg_mod.usage_counters_enabled() is True

    def test_declined_survives_a_real_load(self, tmp_path, monkeypatch):
        path = self._write_config(tmp_path, enabled=False, usage_counters=False)
        cfg_mod = self._load(monkeypatch, path)
        assert cfg_mod.get_config().aether.telemetry.usage_counters is False
        assert cfg_mod.usage_counters_enabled() is False


class _FakeConfig:
    """Minimal stand-in for AetherConfig carrying only the telemetry block."""

    def __init__(self, *, enabled: bool, usage_counters: bool) -> None:
        self.aether = _FakeAetherMeta(enabled=enabled, usage_counters=usage_counters)


class _FakeAetherMeta:
    def __init__(self, *, enabled: bool, usage_counters: bool) -> None:
        self.telemetry = TelemetrySettings(
            enabled=enabled,
            crash_reports=False,
            usage_counters=usage_counters,
        )
