"""
Voice Call view — Aether's headshot with status indicator and live transcript.
This is what plays when in voice mode — NOT the full avatar (that's Video mode).
"""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from src.desktop.theme import (
    BG_VOID,
    USER_COLOR,
    EDGE_BRIGHT,
    EDGE_DARK,
    EDGE_FAINT,
    EDGE_MID,
    EDGE_SUBTLE,
    GRAD_RAISED,
    GRAD_RECESSED,
    ASSISTANT_COLOR,
    R_MD,
    R_XL,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AETHER_HEADSHOT = _PROJECT_ROOT / "models" / "avatar" / "aether_portrait.png"
FALLBACK_HEADSHOT = _PROJECT_ROOT / "assets" / "aether_headshot_placeholder.png"


class VoiceCallView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = "idle"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setStyleSheet(f"background-color: {BG_VOID};")

        # Headshot container — GRAD_RAISED with raised bezel, R_XL radius
        self._headshot_label = QLabel()
        self._headshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._headshot_label.setFixedHeight(200)
        self._headshot_label.setStyleSheet(
            f"background: {GRAD_RAISED};"
            f" border-top: 2px solid {EDGE_BRIGHT};"
            f" border-left: 2px solid {EDGE_MID};"
            f" border-bottom: 1px solid {EDGE_FAINT};"
            f" border-right: 1px solid {EDGE_FAINT};"
            f" border-radius: {R_XL}px;"
        )
        self._load_headshot()
        layout.addWidget(self._headshot_label)

        # Status indicator — 17px (md), TEXT_MUTED when idle
        self._status_label = QLabel("Idle")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setFont(QFont("Montserrat", 13))
        self._status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 17px;")
        layout.addWidget(self._status_label)

        # Transcript header
        transcript_label = QLabel("TRANSCRIPT")
        transcript_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 2px;"
        )
        layout.addWidget(transcript_label)

        # Transcript area — GRAD_RECESSED with recessed bezel, R_MD radius
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {GRAD_RECESSED};"
            f" border-top: 1px solid {EDGE_DARK};"
            f" border-left: 1px solid {EDGE_DARK};"
            f" border-bottom: 1px solid {EDGE_SUBTLE};"
            f" border-right: 1px solid {EDGE_SUBTLE};"
            f" border-radius: {R_MD}px; }}"
        )
        self._transcript_container = QWidget()
        self._transcript_container.setStyleSheet("background: transparent;")
        self._transcript_layout = QVBoxLayout(self._transcript_container)
        self._transcript_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._transcript_layout.setSpacing(6)
        self._transcript_layout.setContentsMargins(10, 10, 10, 10)
        self._scroll.setWidget(self._transcript_container)
        layout.addWidget(self._scroll, stretch=1)

    def _load_headshot(self):
        for path in [AETHER_HEADSHOT, FALLBACK_HEADSHOT]:
            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    scaled = pix.scaled(
                        180,
                        180,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._headshot_label.setPixmap(scaled)
                    return
        self._headshot_label.setText("[ Aether ]")
        self._headshot_label.setStyleSheet(
            f"background: {GRAD_RAISED};"
            f" color: {TEXT_MUTED}; font-size: 15px;"
            f" border-top: 2px solid {EDGE_BRIGHT};"
            f" border-left: 2px solid {EDGE_MID};"
            f" border-bottom: 1px solid {EDGE_FAINT};"
            f" border-right: 1px solid {EDGE_FAINT};"
            f" border-radius: {R_XL}px;"
        )

    def set_status(self, status: str):
        """Update status: 'idle', 'listening', 'speaking', 'thinking'"""
        self._status = status
        labels = {
            "idle": ("Idle", TEXT_MUTED),
            "listening": ("Listening...", "#3498DB"),
            "speaking": ("Speaking...", ASSISTANT_COLOR),
            "thinking": ("Thinking...", "#E67E22"),
        }
        text, color = labels.get(status, ("Idle", TEXT_MUTED))
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 17px;")

    _MAX_TRANSCRIPT_LINES = 100

    def add_transcript_line(self, speaker: str, text: str):
        """Add a line to the live transcript. Trims oldest lines beyond cap."""
        from html import escape

        color = ASSISTANT_COLOR if speaker == "aether" else USER_COLOR
        label_text = f"<b style='color:{color}'>{escape(speaker.title())}:</b> {escape(text)}"
        line = QLabel(label_text)
        line.setWordWrap(True)
        line.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; padding: 2px 0;")
        self._transcript_layout.addWidget(line)

        # Trim oldest lines to prevent unbounded growth
        while self._transcript_layout.count() > self._MAX_TRANSCRIPT_LINES:
            item = self._transcript_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Deferred scroll — wait for layout to update before scrolling
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())

    def clear_transcript(self):
        while self._transcript_layout.count():
            item = self._transcript_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
