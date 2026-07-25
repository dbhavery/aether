"""Settings sandbox — preview how persona changes affect Aether's responses."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.desktop.settings_widgets import (
    COLORS,
    button_qss,
    create_section,
    dialog_qss,
)

# Sample inputs for testing different persona modes
_SAMPLE_INPUTS = [
    "Hey, what's up?",
    "I'm stressed about this deadline.",
    "What do you think about dark mode?",
    "Can you help me with something?",
    "Tell me about yourself.",
]


class SettingsSandbox(QDialog):
    """Preview dialog for testing persona settings before applying."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Settings Sandbox")
        self.setMinimumSize(600, 500)
        self.resize(650, 550)
        self.setStyleSheet(dialog_qss())
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel("Sandbox Preview")
        header.setStyleSheet(f"color: {COLORS['text']}; font-size: 16px; font-weight: bold; background: transparent;")
        layout.addWidget(header)

        desc = QLabel(
            "Test how current persona settings affect responses. "
            "Type a message or use a sample to see how Aether would respond."
        )
        desc.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; background: transparent;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Current settings summary
        summary_group = create_section(layout, "Active Settings")
        summary_layout = QVBoxLayout(summary_group)
        persona = self._config.get("persona", {})

        settings_text = (
            f"Flirtiness: {persona.get('flirtiness', 0.3):.1f}  |  "
            f"Warmth: {persona.get('warmth', 7)}  |  "
            f"Verbosity: {persona.get('verbosity', 5)}  |  "
            f"Formality: {persona.get('formality', 3)}\n"
            f"Backchannels: {'on' if persona.get('backchannels_enabled', True) else 'off'}  |  "
            f"Emotion tracking: {'on' if persona.get('emotion_tracking_enabled', True) else 'off'}  |  "
            f"[SILENT] mode: {persona.get('silent_mode', 'auto')}"
        )
        settings_label = QLabel(settings_text)
        settings_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px; background: transparent;")
        settings_label.setWordWrap(True)
        summary_layout.addWidget(settings_label)

        # Input area
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a test message...")
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {COLORS['input']}; color: {COLORS['text']}; "
            f"border: 1px solid {COLORS['border_dark']}; border-radius: 6px; padding: 8px; }}"
        )
        self._input.returnPressed.connect(self._run_preview)
        input_row.addWidget(self._input, 1)

        run_btn = QPushButton("Test")
        run_btn.setStyleSheet(button_qss(primary=True))
        run_btn.clicked.connect(self._run_preview)
        input_row.addWidget(run_btn)
        layout.addLayout(input_row)

        # Sample buttons
        sample_row = QHBoxLayout()
        sample_label = QLabel("Samples:")
        sample_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; background: transparent;")
        sample_row.addWidget(sample_label)
        for sample in _SAMPLE_INPUTS[:4]:
            btn = QPushButton(sample[:25] + ("..." if len(sample) > 25 else ""))
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                f"QPushButton {{ color: {COLORS['text_dim']}; background: {COLORS['card']}; "
                f"border: 1px solid {COLORS['border_dark']}; border-radius: 4px; "
                f"font-size: 10px; padding: 2px 6px; }}"
                f"QPushButton:hover {{ color: {COLORS['text']}; }}"
            )
            btn.clicked.connect(lambda checked, s=sample: self._test_sample(s))
            sample_row.addWidget(btn)
        sample_row.addStretch()
        layout.addLayout(sample_row)

        # Results area
        self._results = QTextEdit()
        self._results.setReadOnly(True)
        self._results.setStyleSheet(
            f"QTextEdit {{ background: {COLORS['card']}; color: {COLORS['text']}; "
            f"border: 1px solid {COLORS['border_dark']}; border-radius: 8px; "
            f"padding: 12px; font-size: 13px; }}"
        )
        self._results.setPlaceholderText("Preview results will appear here...")
        layout.addWidget(self._results, 1)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(button_qss(primary=False))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _test_sample(self, text: str) -> None:
        self._input.setText(text)
        self._run_preview()

    def _run_preview(self) -> None:
        text = self._input.text().strip()
        if not text:
            return

        persona = self._config.get("persona", {})

        # Build preview showing how settings affect behavior
        lines = [f'Input: "{text}"\n']

        # [SILENT] gate preview
        silent_mode = persona.get("silent_mode", "auto")
        lines.append(f"[SILENT] Mode: {silent_mode}")
        if silent_mode == "auto":
            lines.append("  Gate 1 (speaker verify): PASS (testing as owner)")
            # Simple directed-at-Aether check
            directed = any(w in text.lower() for w in ["aether", "you", "your", "help", "tell", "what"])
            lines.append(
                f"  Gate 2 (intent filter): {'PASS — directed at Aether' if directed else 'UNCERTAIN — would consult LLM'}"
            )
        lines.append("")

        # Emotion tracking preview
        if persona.get("emotion_tracking_enabled", True):
            from src.persona.emotion_tracker import EmotionTracker

            tracker = EmotionTracker()
            snapshot = tracker.analyze(text)
            lines.append(f"Emotion detected: {snapshot.state.value} (energy: {snapshot.energy})")
            hint = tracker.get_tone_hint()
            if hint != "Respond naturally and conversationally.":
                lines.append(f"Tone hint: {hint}")
        else:
            lines.append("Emotion tracking: DISABLED")
        lines.append("")

        # Backchannel preview
        if persona.get("backchannels_enabled", True):
            from src.persona.backchannels import BackchannelManager

            mgr = BackchannelManager()
            bc = mgr.analyze(text)
            lines.append(f"Backchannel: {bc if bc else '(none — no trigger detected)'}")
        else:
            lines.append("Backchannels: DISABLED")
        lines.append("")

        # Filler preview
        from src.persona.fillers import FillerGenerator

        filler_gen = FillerGenerator()
        complexity = filler_gen.classify_complexity(text)
        filler = filler_gen.get_filler(text)
        lines.append(f"Complexity: {complexity}")
        lines.append(f"Filler: {filler if filler else '(none — simple query)'}")
        lines.append("")

        # Response formatting preview
        flirt = persona.get("flirtiness", 0.3)
        warmth = persona.get("warmth", 7)
        lines.append(f"Persona: flirtiness={flirt}, warmth={warmth}")
        if flirt > 0.5:
            lines.append("  Warmth level: HIGH — playful, flirty undertones")
        elif flirt > 0.2:
            lines.append("  Warmth level: MODERATE — casual, subtly warm")
        else:
            lines.append("  Warmth level: LOW — professional, neutral")

        # Sanitizer preview
        from src.brain.sanitizer import sanitize_response

        test_response = f"That's a great question! I'm happy to help you with that. {text}"
        sanitized = sanitize_response(test_response)
        lines.append("\nSanitizer test:")
        lines.append(f'  Before: "{test_response}"')
        lines.append(f'  After:  "{sanitized}"')

        self._results.setPlainText("\n".join(lines))
