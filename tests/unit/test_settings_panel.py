"""Tests for the settings panel — config round-trip and widget mapping."""

import pytest


class TestSettingsConfig:
    """Test config read/write without requiring Qt."""

    def test_get_nested_simple(self):
        from src.desktop.settings_panel import SettingsPanel

        d = {"audio": {"sample_rate": 16000}}
        panel = SettingsPanel.__new__(SettingsPanel)
        assert panel._get_nested(d, "audio.sample_rate") == 16000

    def test_get_nested_missing(self):
        from src.desktop.settings_panel import SettingsPanel

        d = {"audio": {"sample_rate": 16000}}
        panel = SettingsPanel.__new__(SettingsPanel)
        assert panel._get_nested(d, "audio.missing_key") is None

    def test_get_nested_deep(self):
        from src.desktop.settings_panel import SettingsPanel

        d = {"desktop": {"theme": {"background": "#282828"}}}
        panel = SettingsPanel.__new__(SettingsPanel)
        assert panel._get_nested(d, "desktop.theme.background") == "#282828"

    def test_set_nested_creates_path(self):
        from src.desktop.settings_panel import SettingsPanel

        d = {}
        panel = SettingsPanel.__new__(SettingsPanel)
        panel._set_nested(d, "persona.warmth", 7)
        assert d == {"persona": {"warmth": 7}}

    def test_set_nested_overwrites(self):
        from src.desktop.settings_panel import SettingsPanel

        d = {"persona": {"warmth": 5, "verbosity": 3}}
        panel = SettingsPanel.__new__(SettingsPanel)
        panel._set_nested(d, "persona.warmth", 9)
        assert d["persona"]["warmth"] == 9
        assert d["persona"]["verbosity"] == 3

    def test_format_slider_no_decimals(self):
        from src.desktop.settings_widgets import format_slider_value

        assert format_slider_value(7, 0) == "7"

    def test_format_slider_two_decimals(self):
        from src.desktop.settings_widgets import format_slider_value

        assert format_slider_value(75, 2) == "0.75"

    def test_format_slider_one_decimal(self):
        from src.desktop.settings_widgets import format_slider_value

        assert format_slider_value(5, 1) == "0.5"


class TestConfigRoundTrip:
    """Test that config can be saved and reloaded."""

    def test_yaml_roundtrip_preserves_values(self, tmp_path):
        config_content = """server:
  websocket_port: 8765
  health_port: 8767
persona:
  warmth: 7
  verbosity: 5
"""
        config_file = tmp_path / "aether_config.yaml"
        config_file.write_text(config_content)

        from src.desktop.settings_panel import SettingsPanel

        panel = SettingsPanel.__new__(SettingsPanel)

        # Override CONFIG_PATH for test
        import src.desktop.settings_panel as sp

        original_path = sp.CONFIG_PATH
        sp.CONFIG_PATH = config_file
        try:
            config = panel._load_config()
            assert config["server"]["websocket_port"] == 8765
            assert config["persona"]["warmth"] == 7

            # Modify and save
            panel._config = config
            panel._config["persona"]["warmth"] = 9
            panel._widgets = {}  # No widgets to collect
            panel._save_config()

            # Reload and verify
            config2 = panel._load_config()
            assert config2["persona"]["warmth"] == 9
            assert config2["server"]["websocket_port"] == 8765
        finally:
            sp.CONFIG_PATH = original_path

    @pytest.mark.skipif(not __import__("importlib").util.find_spec("ruamel.yaml"), reason="ruamel.yaml not installed")
    def test_ruamel_preserves_comments(self, tmp_path):
        config_content = """# Main config
server:
  websocket_port: 8765  # Default WS port
  health_port: 8767
"""
        config_file = tmp_path / "aether_config.yaml"
        config_file.write_text(config_content)

        from ruamel.yaml import YAML

        ry = YAML()
        ry.preserve_quotes = True
        with open(config_file) as f:
            data = ry.load(f)
        data["server"]["websocket_port"] = 9999
        with open(config_file, "w") as f:
            ry.dump(data, f)

        text = config_file.read_text()
        assert "# Main config" in text
        assert "# Default WS port" in text
        assert "9999" in text


class TestNewEventTypes:
    """Verify the 3 new EventTypes exist."""

    def test_settings_changed_exists(self):
        from src.shared.types import EventType

        assert EventType.SETTINGS_CHANGED == "settings_changed"

    def test_proactive_message_exists(self):
        from src.shared.types import EventType

        assert EventType.PROACTIVE_MESSAGE == "proactive_message"

    def test_memory_correction_exists(self):
        from src.shared.types import EventType

        assert EventType.MEMORY_CORRECTION == "memory_correction"


class TestConfigReload:
    """Test config cache invalidation."""

    def test_reload_yaml_config_clears_cache(self):
        from src.shared.config import get_yaml_config, reload_yaml_config

        # First call caches
        config1 = get_yaml_config()
        # Reload clears and re-reads
        config2 = reload_yaml_config()
        assert config2["server"]["websocket_port"] == config1["server"]["websocket_port"]


class TestSettingsSandbox:
    """Test the settings sandbox preview logic (no Qt required)."""

    def test_sandbox_imports(self):
        from src.desktop.settings_sandbox import SettingsSandbox

        assert SettingsSandbox is not None

    def test_sample_inputs_exist(self):
        from src.desktop.settings_sandbox import _SAMPLE_INPUTS

        assert len(_SAMPLE_INPUTS) >= 4
        assert all(isinstance(s, str) for s in _SAMPLE_INPUTS)

    def test_settings_panel_has_all_sections(self):
        """Verify settings panel has all expected section builders."""
        from src.desktop.settings_panel import SettingsPanel

        panel_cls = SettingsPanel
        expected_sections = [
            "_build_connection_section",
            "_build_voice_section",
            "_build_voice_pipeline_section",
            "_build_persona_section",
            "_build_llm_section",
            "_build_notifications_section",
            "_build_memory_section",
            "_build_tools_section",
            "_build_avatar_section",
            "_build_security_section",
            "_build_appearance_section",
            "_build_api_keys_section",
            "_build_about_section",
        ]
        for section in expected_sections:
            assert hasattr(panel_cls, section), f"Missing section: {section}"

    def test_settings_panel_sandbox_button(self):
        """Verify sandbox button handler exists."""
        from src.desktop.settings_panel import SettingsPanel

        assert hasattr(SettingsPanel, "_open_sandbox")

    def test_new_widget_keys_registered(self):
        """Verify new config keys for voice pipeline, tools, avatar."""
        from src.desktop.settings_panel import SettingsPanel

        # Create panel without __init__ to inspect methods
        panel = SettingsPanel.__new__(SettingsPanel)
        panel._widgets = {}
        panel._config = {
            "voice": {"barge_in_enabled": True},
            "avatar": {"enabled": True},
        }

        # Verify the methods exist that populate new widget keys
        assert callable(getattr(panel, "_build_voice_pipeline_section", None))
        assert callable(getattr(panel, "_build_tools_section", None))
        assert callable(getattr(panel, "_build_avatar_section", None))
