"""Settings panel — reads/writes aether_config.yaml with comment preservation."""

import os
import subprocess
import tempfile
from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from src.desktop.settings_widgets import (
    COLORS,
    button_qss,
    create_section,
    dialog_qss,
    labeled_checkbox,
    labeled_combo,
    labeled_line_edit,
    labeled_slider,
    labeled_spinbox,
    labeled_time_edit,
)

try:
    from ruamel.yaml import YAML

    _RUAMEL_AVAILABLE = True
except ImportError:
    _RUAMEL_AVAILABLE = False

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "aether_config.yaml"


class SettingsPanel(QDialog):
    """Modal settings dialog — all config sections as collapsible groups."""

    settings_saved = Signal()

    def __init__(self, ws_client=None, parent=None):
        super().__init__(parent)
        self._ws = ws_client
        self.setWindowTitle("Settings")
        self.setMinimumSize(500, 700)
        self.resize(520, 750)
        self.setStyleSheet(dialog_qss())

        self._config = self._load_config()
        self._widgets: dict[str, QWidget] = {}

        self._setup_ui()
        self._populate_from_config()

    # ── Config I/O ──────────────────────────────────────────────

    def _load_config(self) -> dict:
        if not CONFIG_PATH.exists():
            logger.error(f"Settings: config not found at {CONFIG_PATH}")
            return {}
        if _RUAMEL_AVAILABLE:
            ry = YAML()
            ry.preserve_quotes = True
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return dict(ry.load(f) or {})
        else:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                import yaml

                return yaml.safe_load(f) or {}

    def _save_config(self) -> None:
        import contextlib

        self._collect_to_config()
        # Atomic write: write to temp file then os.replace() to prevent data loss on crash
        config_dir = CONFIG_PATH.parent
        fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".yaml.tmp", prefix=".settings_")
        os.close(fd)  # Close fd from mkstemp — we'll reopen via Path
        tmp = Path(tmp_path)
        try:
            if _RUAMEL_AVAILABLE:
                ry = YAML()
                ry.preserve_quotes = True
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    data = ry.load(f)
                self._merge_into_ruamel(data, self._config)
                with open(tmp, "w", encoding="utf-8") as f:
                    ry.dump(data, f)
            else:
                import yaml

                with open(tmp, "w", encoding="utf-8") as f:
                    yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)
            os.replace(tmp, CONFIG_PATH)
            logger.info("Settings: config saved to aether_config.yaml")
        except Exception:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise

    def _merge_into_ruamel(self, target, source) -> None:
        """Recursively merge source dict into ruamel CommentedMap preserving comments."""
        for key, val in source.items():
            if isinstance(val, dict) and key in target and isinstance(target[key], dict):
                self._merge_into_ruamel(target[key], val)
            else:
                target[key] = val

    # ── UI Setup ────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)

        self._build_connection_section()
        self._build_voice_section()
        self._build_voice_pipeline_section()
        self._build_persona_section()
        self._build_llm_section()
        self._build_notifications_section()
        self._build_memory_section()
        self._build_tools_section()
        self._build_avatar_section()
        self._build_security_section()
        self._build_appearance_section()
        self._build_api_keys_section()
        self._build_about_section()

        self._layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        # Button bar
        btn_bar = QFrame()
        btn_bar.setStyleSheet(f"QFrame {{ background: {COLORS['card']}; border-top: 1px solid #444; }}")
        btn_bar.setFixedHeight(56)
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(16, 8, 16, 8)

        btn_layout.addStretch()

        preview_btn = QPushButton("Sandbox")
        preview_btn.setStyleSheet(button_qss(primary=False))
        preview_btn.setToolTip("Preview how persona changes affect responses")
        preview_btn.clicked.connect(self._open_sandbox)
        btn_layout.addWidget(preview_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(button_qss(primary=False))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(button_qss(primary=True))
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        outer.addWidget(btn_bar)

    # ── Section Builders ────────────────────────────────────────

    def _build_connection_section(self) -> None:
        group = create_section(self._layout, "Connection")
        layout = QVBoxLayout(group)
        self._widgets["server.host"] = labeled_line_edit(layout, "Host", "localhost")
        self._widgets["server.websocket_port"] = labeled_spinbox(layout, "Port", 1, 65535, 8765)
        self._widgets["desktop.auto_reconnect"] = labeled_checkbox(layout, "Auto-reconnect", True)
        self._widgets["desktop.reconnect_interval"] = labeled_spinbox(layout, "Reconnect interval (s)", 1, 60, 3)

    def _build_voice_section(self) -> None:
        group = create_section(self._layout, "Voice")
        layout = QVBoxLayout(group)
        self._widgets["audio.wake_word_sensitivity"] = labeled_slider(
            layout, "Wake word sensitivity", 0, 100, 70, decimals=2
        )
        self._widgets["voice.voice_stability"] = labeled_slider(layout, "Voice stability", 0, 100, 50, decimals=2)
        self._widgets["voice.voice_similarity"] = labeled_slider(layout, "Voice similarity", 0, 100, 75, decimals=2)
        self._widgets["voice.tts_speed"] = labeled_slider(layout, "TTS speed", 50, 200, 100, decimals=2)
        self._widgets["audio.input_device"] = labeled_combo(layout, "Input device", self._get_audio_devices("input"))
        self._widgets["audio.output_device"] = labeled_combo(layout, "Output device", self._get_audio_devices("output"))
        self._widgets["persona.backchannel_probability"] = labeled_slider(
            layout, "Backchannel probability", 0, 100, 0, decimals=2
        )

    def _build_voice_pipeline_section(self) -> None:
        group = create_section(self._layout, "Voice Pipeline")
        layout = QVBoxLayout(group)
        self._widgets["audio.vad_threshold"] = labeled_slider(layout, "VAD threshold", 0, 100, 50, decimals=2)
        self._widgets["voice.barge_in_enabled"] = labeled_checkbox(layout, "Barge-in (interrupt Aether)", True)
        self._widgets["voice.barge_in_delay_ms"] = labeled_spinbox(layout, "Barge-in delay (ms)", 100, 1000, 300)
        self._widgets["voice.echo_cancel_ring_down_ms"] = labeled_spinbox(
            layout, "Echo cancel ring-down (ms)", 50, 500, 200
        )
        self._widgets["voice.auto_sleep_minutes"] = labeled_spinbox(layout, "Auto-sleep (min)", 1, 60, 10)

    def _build_persona_section(self) -> None:
        group = create_section(self._layout, "Persona")
        layout = QVBoxLayout(group)
        self._widgets["persona.warmth"] = labeled_slider(layout, "Warmth", 1, 10, 7, decimals=0)
        self._widgets["persona.verbosity"] = labeled_slider(layout, "Verbosity", 1, 10, 5, decimals=0)
        self._widgets["persona.flirtiness"] = labeled_slider(layout, "Flirtiness", 1, 10, 4, decimals=0)
        self._widgets["persona.formality"] = labeled_slider(layout, "Formality", 1, 10, 3, decimals=0)
        self._widgets["persona.voice_brief_text_verbose"] = labeled_checkbox(
            layout, "Voice mode: brief / Text mode: verbose", True
        )
        self._widgets["persona.backchannels_enabled"] = labeled_checkbox(layout, "Backchannels in voice mode", True)
        self._widgets["persona.emotion_tracking_enabled"] = labeled_checkbox(
            layout, "Emotion tracking (tone adjustment)", True
        )
        modes = ["auto", "manual"]
        self._widgets["persona.silent_mode"] = labeled_combo(layout, "[SILENT] mode", modes)

    def _build_llm_section(self) -> None:
        group = create_section(self._layout, "LLM")
        layout = QVBoxLayout(group)
        tiers = ["FAST", "CLAUDE", "CLAUDE_HEAVY", "GEMINI", "GEMINI_FAST", "GEMINI_PRO"]
        self._widgets["llm.selected_tier"] = labeled_combo(layout, "Default tier", tiers)
        self._widgets["llm.fast_model"] = labeled_line_edit(layout, "Fast model", "qwen3:8b")
        self._widgets["llm.claude_model"] = labeled_line_edit(layout, "Claude model", "claude-sonnet-4-6")
        self._widgets["llm.gemini_model"] = labeled_line_edit(layout, "Gemini model", "gemini-2.5-flash")
        self._widgets["llm.max_tokens"] = labeled_spinbox(layout, "Max tokens", 128, 16384, 2048)
        self._widgets["llm.adaptive_thinking"] = labeled_checkbox(layout, "Adaptive thinking (Sonnet/Opus)", False)

    def _build_notifications_section(self) -> None:
        group = create_section(self._layout, "Notifications")
        layout = QVBoxLayout(group)
        self._widgets["notifications.daily_briefing_time"] = labeled_time_edit(
            layout, "Daily briefing time", QTime(8, 0)
        )
        self._widgets["notifications.evening_time"] = labeled_time_edit(layout, "Evening check-in time", QTime(21, 0))
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        self._widgets["notifications.weekly_digest_day"] = labeled_combo(layout, "Weekly digest day", days)
        self._widgets["notifications.sound_enabled"] = labeled_checkbox(layout, "Sound on notification", False)
        self._widgets["notifications.max_proactive_per_day"] = labeled_spinbox(
            layout, "Max proactive messages/day", 0, 20, 3
        )

    def _build_memory_section(self) -> None:
        group = create_section(self._layout, "Memory")
        layout = QVBoxLayout(group)
        self._widgets["memory.vram_cache_mb"] = labeled_spinbox(layout, "VRAM cache (MB)", 64, 16384, 512)
        self._widgets["memory.ram_cache_mb"] = labeled_spinbox(layout, "RAM cache (MB)", 512, 32768, 5120)
        self._widgets["memory.auto_save_interval"] = labeled_spinbox(layout, "Auto-save interval (s)", 10, 600, 60)
        self._widgets["memory.top_k_results"] = labeled_spinbox(layout, "Search top-K results", 1, 20, 5)

    def _build_tools_section(self) -> None:
        group = create_section(self._layout, "Tools")
        layout = QVBoxLayout(group)
        self._widgets["llm.timeout_fast_seconds"] = labeled_spinbox(layout, "Fast timeout (s)", 5, 60, 15)
        self._widgets["llm.timeout_primary_seconds"] = labeled_spinbox(layout, "Primary timeout (s)", 15, 120, 45)
        self._widgets["llm.timeout_heavy_seconds"] = labeled_spinbox(layout, "Heavy timeout (s)", 30, 300, 120)

        note = QLabel("Allowed apps, blocked paths, and blocked commands are managed in aether_config.yaml.")
        note.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _build_avatar_section(self) -> None:
        group = create_section(self._layout, "Avatar")
        layout = QVBoxLayout(group)
        self._widgets["avatar.enabled"] = labeled_checkbox(layout, "Avatar enabled", True)
        self._widgets["avatar.stream_url"] = labeled_line_edit(layout, "Stream URL", "http://localhost:8770/stream")
        self._widgets["avatar.target_fps"] = labeled_spinbox(layout, "Target FPS", 10, 60, 25)
        self._widgets["avatar.stream_width"] = labeled_spinbox(layout, "Stream width", 256, 1024, 512)
        self._widgets["avatar.stream_height"] = labeled_spinbox(layout, "Stream height", 256, 1024, 512)

    def _build_security_section(self) -> None:
        group = create_section(self._layout, "Security")
        layout = QVBoxLayout(group)
        self._widgets["security.wake_word_enabled"] = labeled_checkbox(layout, "Wake word enabled", True)
        self._widgets["audio.speaker_verify_threshold"] = labeled_slider(
            layout, "Speaker verification threshold", 0, 100, 75, decimals=2
        )
        self._widgets["security.camera_privacy"] = labeled_checkbox(layout, "Camera privacy mode", False)
        self._widgets["security.mic_mute"] = labeled_checkbox(layout, "Mic mute", False)

    def _build_appearance_section(self) -> None:
        group = create_section(self._layout, "Appearance")
        layout = QVBoxLayout(group)
        combo = labeled_combo(layout, "Theme", ["Dark"])
        combo.setEnabled(False)
        self._widgets["desktop.theme_name"] = combo
        self._widgets["desktop.show_on_startup"] = labeled_checkbox(layout, "Show window on startup", True)
        self._widgets["desktop.always_on_top"] = labeled_checkbox(layout, "Always on top", True)
        self._widgets["desktop.opacity"] = labeled_slider(layout, "Window opacity", 50, 100, 100, decimals=2)

    def _build_api_keys_section(self) -> None:
        group = create_section(self._layout, "API Keys")
        layout = QVBoxLayout(group)
        note = QLabel("Manage API keys for external services. Opens a dedicated panel.")
        note.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; font-size: 12px;")
        note.setWordWrap(True)
        layout.addWidget(note)
        manage_btn = QPushButton("Manage API Keys...")
        manage_btn.setStyleSheet(button_qss(primary=True))
        manage_btn.clicked.connect(self._open_api_keys_dialog)
        layout.addWidget(manage_btn)

    def _open_api_keys_dialog(self) -> None:
        from src.desktop.settings_api_tab import ApiKeysTab

        dlg = QDialog(self)
        dlg.setWindowTitle("API Keys")
        dlg.setMinimumSize(600, 700)
        dlg.resize(650, 750)
        dlg.setStyleSheet(f"QDialog {{ background: {COLORS['bg']}; }}")
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(0, 0, 0, 0)
        tab = ApiKeysTab()
        dlg_layout.addWidget(tab)
        dlg.exec()

    def _build_about_section(self) -> None:
        group = create_section(self._layout, "About")
        layout = QVBoxLayout(group)
        version_label = QLabel("Version: 1.0.0")
        version_label.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
        layout.addWidget(version_label)

        git_hash = self._get_git_hash()
        hash_label = QLabel(f"Commit: {git_hash}")
        hash_label.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
        layout.addWidget(hash_label)

        update_btn = QPushButton("Check for updates")
        update_btn.setEnabled(False)
        update_btn.setStyleSheet(button_qss(primary=False))
        layout.addWidget(update_btn)

    # ── Config ↔ Widget Mapping ─────────────────────────────────

    def _populate_from_config(self) -> None:
        """Load config values into widgets."""
        for key, widget in self._widgets.items():
            val = self._get_nested(self._config, key)
            if val is None:
                continue
            try:
                if isinstance(widget, QSlider):
                    decimals = widget.property("decimals") or 0
                    if decimals > 0:
                        scale = 10**decimals
                        widget.setValue(int(float(val) * scale))
                    else:
                        widget.setValue(int(val))
                elif isinstance(widget, QSpinBox):
                    widget.setValue(int(val))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(val))
                elif isinstance(widget, QComboBox):
                    idx = widget.findText(str(val))
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                elif isinstance(widget, QLineEdit):
                    widget.setText(str(val))
                elif isinstance(widget, QTimeEdit):
                    if isinstance(val, str) and ":" in val:
                        parts = val.split(":")
                        widget.setTime(QTime(int(parts[0]), int(parts[1])))
            except (ValueError, TypeError) as e:
                logger.debug(f"Settings: skipping {key}: {e}")

    def _collect_to_config(self) -> None:
        """Read widget values back into config dict."""
        for key, widget in self._widgets.items():
            try:
                if isinstance(widget, QSlider):
                    decimals = widget.property("decimals") or 0
                    if decimals > 0:
                        scale = 10**decimals
                        val = widget.value() / scale
                    else:
                        val = widget.value()
                elif isinstance(widget, QSpinBox):
                    val = widget.value()
                elif isinstance(widget, QCheckBox):
                    val = widget.isChecked()
                elif isinstance(widget, QComboBox):
                    val = widget.currentText()
                elif isinstance(widget, QLineEdit):
                    val = widget.text()
                elif isinstance(widget, QTimeEdit):
                    t = widget.time()
                    val = f"{t.hour():02d}:{t.minute():02d}"
                else:
                    continue
                self._set_nested(self._config, key, val)
            except Exception as e:
                logger.error(f"Settings: failed to collect {key}: {e}")

    def _get_nested(self, d: dict, dotted_key: str):
        """Get value from nested dict using dotted key like 'audio.sample_rate'."""
        keys = dotted_key.split(".")
        current = d
        for k in keys:
            if not isinstance(current, dict) or k not in current:
                return None
            current = current[k]
        return current

    def _set_nested(self, d: dict, dotted_key: str, value) -> None:
        """Set value in nested dict using dotted key."""
        keys = dotted_key.split(".")
        current = d
        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    # ── Actions ─────────────────────────────────────────────────

    def _on_save(self) -> None:
        self._save_config()
        # Notify server via WebSocket (desktop runs in separate process from server)
        if self._ws and self._ws.is_connected:
            self._ws.send_json({"type": "settings_changed"})
        self.settings_saved.emit()
        self.accept()

    def _open_sandbox(self) -> None:
        """Open the settings sandbox — preview how persona changes affect responses."""
        from src.desktop.settings_sandbox import SettingsSandbox

        self._collect_to_config()
        sandbox = SettingsSandbox(config=self._config, parent=self)
        sandbox.exec()

    # ── Helpers ──────────────────────────────────────────────────

    def _get_audio_devices(self, direction: str) -> list[str]:
        """Get available audio devices. Returns ['System Default'] on error."""
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            result = ["System Default"]
            for i, dev in enumerate(devices):
                if (direction == "input" and dev["max_input_channels"] > 0) or (
                    direction == "output" and dev["max_output_channels"] > 0
                ):
                    result.append(f"[{i}] {dev['name']}")
            return result
        except Exception:
            return ["System Default"]

    def _get_git_hash(self) -> str:
        try:
            result = subprocess.run(  # nosec B603 B607  # trusted git command
                ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"
