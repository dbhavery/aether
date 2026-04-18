"""Chat view — text conversation with Aether."""

from datetime import datetime
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.desktop.theme import (
    ASSISTANT_COLOR,
    BG_VOID,
    EDGE_BRIGHT,
    EDGE_FAINT,
    GRAD_BAR,
    GRAD_RAISED,
    R_XL,
    TEXT_FAINT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    USER_COLOR,
    input_qss,
    send_button_qss,
)


class ChatBubble(QFrame):
    """Single chat message bubble — neumorphic raised style."""

    def __init__(self, text: str, is_assistant: bool, timestamp: str = "", parent=None):
        super().__init__(parent)
        color = ASSISTANT_COLOR if is_assistant else USER_COLOR
        name = "Aether" if is_assistant else "User"
        self.setStyleSheet(f"""
            QFrame {{
                background: {GRAD_RAISED};
                border-top: 2px solid {EDGE_BRIGHT};
                border-left: 3px solid {color};
                border-bottom: 1px solid {EDGE_FAINT};
                border-right: 1px solid {EDGE_FAINT};
                border-radius: {R_XL}px;
                padding: 0;
                margin: 2px 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Name label — uppercase, semibold, letter-spacing 2px
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: 600;"
            f" text-transform: uppercase; letter-spacing: 2px;"
            f" background: transparent; border: none;"
        )
        layout.addWidget(name_label)

        # Message text — base size 15px, HTML-escaped to prevent injection
        msg_label = QLabel(escape(text))
        msg_label.setWordWrap(True)
        msg_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 15px; background: transparent; border: none;")
        layout.addWidget(msg_label)

        # Timestamp — TEXT_FAINT, 11px
        if timestamp:
            time_label = QLabel(timestamp)
            time_label.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 11px; background: transparent; border: none;")
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(time_label)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMaximumWidth(500)


_MAX_CHAT_BUBBLES = 200


class ChatView(QWidget):
    """Text chat view — the default home screen."""

    message_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Chat area — BG_VOID background (not BG_SURFACE)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: {BG_VOID}; }}")

        self._chat_container = QWidget()
        self._chat_container.setStyleSheet(f"background-color: {BG_VOID};")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(16, 16, 16, 16)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch()

        self._scroll.setWidget(self._chat_container)
        layout.addWidget(self._scroll, 1)

        # Input area — GRAD_BAR for the frame, GRAD_INPUT for the input well
        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            QFrame {{
                background: {GRAD_BAR};
                border-top: 1px solid {EDGE_FAINT};
            }}
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(16, 12, 16, 12)
        input_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message Aether...")
        self._input.setStyleSheet(input_qss())
        self._input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self._input, 1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setStyleSheet(send_button_qss())
        self._send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self._send_btn)

        layout.addWidget(input_frame)

    def add_message(self, text: str, is_assistant: bool, is_interim: bool = False) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        bubble = ChatBubble(text, is_assistant, timestamp)
        if is_interim:
            bubble.setObjectName("interim_bubble")
            bubble.setStyleSheet(
                bubble.styleSheet() + " QLabel { color: rgba(255, 255, 255, 120); font-style: italic; }"
            )

        # Insert before the stretch
        count = self._chat_layout.count()
        self._chat_layout.insertWidget(count - 1, bubble)

        # Trim oldest bubbles to prevent unbounded memory growth
        # count - 1 excludes the trailing stretch item
        while self._chat_layout.count() - 1 > _MAX_CHAT_BUBBLES:
            item = self._chat_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Auto-scroll to bottom
        from PySide6.QtCore import QTimer

        QTimer.singleShot(50, self._scroll_to_bottom)

    def remove_interim_messages(self) -> None:
        for i in range(self._chat_layout.count() - 1, -1, -1):
            item = self._chat_layout.itemAt(i)
            if item and item.widget() and item.widget().objectName() == "interim_bubble":
                widget = item.widget()
                self._chat_layout.removeWidget(widget)
                widget.deleteLater()

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.add_message(text, is_assistant=False)
        self.message_submitted.emit(text)

    def _scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_input_enabled(self, enabled: bool) -> None:
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)
