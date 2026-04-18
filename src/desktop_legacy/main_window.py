"""Main window — Aether desktop client."""

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from src.desktop.chat_view import ChatView
from src.desktop.settings_panel import SettingsPanel
from src.desktop.task_panel import TaskPanel
from src.desktop.theme import (
    ASSISTANT_COLOR,
    COLOR_ERROR,
    COLOR_SUCCESS,
    EDGE_BRIGHT,
    EDGE_FAINT,
    GLOBAL_QSS,
    GRAD_BAR,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    mode_button_qss,
)
from src.desktop.video_view import VideoView
from src.desktop.voice_call_view import VoiceCallView
from src.desktop.ws_client import WebSocketClient


class MainWindow(QMainWindow):
    """Aether desktop client — dark neumorphic theme, bottom-right, always on top."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aether")
        self.setMinimumSize(420, 600)
        self.resize(420, 650)
        self.setStyleSheet(GLOBAL_QSS)

        # Tray state — set by app.py after construction
        self._tray: QSystemTrayIcon | None = None
        self._force_quit = False
        self._pending_approval_id: str | None = None

        # Always on top
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)

        # WebSocket client
        self._ws = WebSocketClient()
        self._ws.connected.connect(self._on_ws_connected)
        self._ws.disconnected.connect(self._on_ws_disconnected)
        self._ws.message_received.connect(self._on_ws_message)
        self._ws.error_occurred.connect(self._on_ws_error)

        self._setup_ui()
        self._position_bottom_right()
        self._ws.connect_to_server()

    def set_tray_icon(self, tray: QSystemTrayIcon) -> None:
        """Called by app.py to register the system tray icon."""
        self._tray = tray

    def show_from_tray(self) -> None:
        """Show and raise the window from the system tray."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_application(self) -> None:
        """Truly quit — called from tray menu or when no tray is available."""
        self._force_quit = True
        self._video_view.stop()
        self._ws.disconnect_from_server()
        if self._tray:
            self._tray.hide()
        app = QApplication.instance()
        if app:
            app.quit()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar — GRAD_BAR gradient, border-bottom 1px EDGE_FAINT
        title_bar = QFrame()
        title_bar.setStyleSheet(f"""
            QFrame {{
                background: {GRAD_BAR};
                border-bottom: 1px solid {EDGE_FAINT};
            }}
        """)
        title_bar.setFixedHeight(48)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)

        # Title text — 17px, TEXT_SECONDARY, uppercase, letter-spacing 0.15em, weight 300
        title_label = QLabel("AETHER")
        title_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 17px; font-weight: 300;"
            f" letter-spacing: 0.15em; background: transparent;"
        )
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # Status label — TEXT_MUTED, 13px
        self._status_label = QLabel("Connecting...")
        self._status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        title_layout.addWidget(self._status_label)

        # Tasks button — TEXT_FAINT normally, TEXT_PRIMARY on hover
        tasks_btn = QPushButton("Tasks")
        tasks_btn.setFixedSize(48, 32)
        tasks_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_FAINT};
                font-size: 11px;
                border: none;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
            }}
        """)
        tasks_btn.setToolTip("Agent Tasks")
        tasks_btn.clicked.connect(self._toggle_tasks)
        title_layout.addWidget(tasks_btn)

        # Gear button — TEXT_FAINT normally, TEXT_PRIMARY on hover
        gear_btn = QPushButton("\u2699")
        gear_btn.setFixedSize(32, 32)
        gear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_FAINT};
                font-size: 18px;
                border: none;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
            }}
        """)
        gear_btn.setToolTip("Settings")
        gear_btn.clicked.connect(self._open_settings)
        title_layout.addWidget(gear_btn)
        layout.addWidget(title_bar)

        # Stacked widget: Chat (0) + Voice (1) + Video (2)
        self._stack = QStackedWidget()

        self._chat_view = ChatView()
        self._chat_view.message_submitted.connect(self._on_send_message)
        self._stack.addWidget(self._chat_view)

        self._voice_view = VoiceCallView()
        self._stack.addWidget(self._voice_view)

        self._video_view = VideoView()
        self._stack.addWidget(self._video_view)

        self._task_panel = TaskPanel()
        self._stack.addWidget(self._task_panel)  # index 3

        layout.addWidget(self._stack, 1)

        # Mode bar — GRAD_BAR, border-top 2px EDGE_BRIGHT (light catches from above)
        mode_bar = QFrame()
        mode_bar.setStyleSheet(f"""
            QFrame {{
                background: {GRAD_BAR};
                border-top: 2px solid {EDGE_BRIGHT};
            }}
        """)
        mode_bar.setFixedHeight(44)
        mode_layout = QHBoxLayout(mode_bar)
        mode_layout.setContentsMargins(16, 4, 16, 4)
        mode_layout.setSpacing(8)

        mode_layout.addStretch()

        self._text_btn = QPushButton("Chat")
        self._text_btn.setStyleSheet(mode_button_qss(active=True))
        self._text_btn.clicked.connect(lambda: self._switch_mode(0))
        mode_layout.addWidget(self._text_btn)

        self._voice_btn = QPushButton("Voice")
        self._voice_btn.setStyleSheet(mode_button_qss(active=False))
        self._voice_btn.clicked.connect(lambda: self._switch_mode(1))
        mode_layout.addWidget(self._voice_btn)

        self._video_btn = QPushButton("Video")
        self._video_btn.setStyleSheet(mode_button_qss(active=False))
        self._video_btn.clicked.connect(lambda: self._switch_mode(2))
        mode_layout.addWidget(self._video_btn)

        mode_layout.addStretch()
        layout.addWidget(mode_bar)

    def _position_bottom_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 20
            y = geo.bottom() - self.height() - 95
            self.move(x, y)

    def _on_ws_connected(self) -> None:
        self._status_label.setText("Connected")
        self._status_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 13px; background: transparent;")
        self._chat_view.set_input_enabled(True)

    def _on_ws_disconnected(self) -> None:
        self._status_label.setText("Disconnected — reconnecting...")
        self._status_label.setStyleSheet(f"color: {COLOR_ERROR}; font-size: 13px; background: transparent;")
        self._chat_view.set_input_enabled(False)

    def _on_ws_error(self, msg: str) -> None:
        logger.error(f"Desktop WS error: {msg}")

    def _open_settings(self) -> None:
        """Open the settings dialog."""
        dialog = SettingsPanel(ws_client=self._ws, parent=self)
        dialog.exec()

    def _toggle_tasks(self) -> None:
        """Toggle the task panel view."""
        if self._stack.currentIndex() == 3:
            self._switch_mode(0)  # Back to chat
        else:
            self._switch_mode(3)

    def _switch_mode(self, index: int) -> None:
        """Switch between Chat (0), Voice (1), and Video (2) views."""
        previous = self._stack.currentIndex()

        # Stop video stream when leaving video mode
        if previous == 2 and index != 2:
            self._video_view.pause_stream()

        self._stack.setCurrentIndex(index)
        self._text_btn.setStyleSheet(mode_button_qss(active=(index == 0)))
        self._voice_btn.setStyleSheet(mode_button_qss(active=(index == 1)))
        self._video_btn.setStyleSheet(mode_button_qss(active=(index == 2)))

        # Resume video stream when entering video mode
        if index == 2 and previous != 2:
            self._video_view.resume_stream()

        # Notify server of mode change
        mode_name = ["text", "voice", "video"][index] if index < 3 else "tasks"
        self._ws.send_json({"type": "mode_change", "mode": mode_name})

    def _on_ws_message(self, data: dict) -> None:
        msg_type = data.get("type", "")

        # Handle wake word indicator
        if msg_type == "wake_word":
            self._status_label.setText("Listening...")
            self._status_label.setStyleSheet(f"color: {ASSISTANT_COLOR}; font-size: 13px; background: transparent;")
            self._voice_view.set_status("listening")
            return

        # Handle error messages from server
        if msg_type == "error":
            error_text = data.get("text", data.get("message", "Unknown error"))
            logger.warning(f"Desktop: server error: {error_text}")
            self._chat_view.add_message(f"[Error] {error_text}", is_assistant=True)
            self._status_label.setText("Error")
            self._status_label.setStyleSheet(f"color: {COLOR_ERROR}; font-size: 13px; background: transparent;")
            return

        # Handle approval requests from server
        if msg_type == "approval_request":
            approval_id = data.get("approval_id", "")
            description = str(data.get("description", ""))[:500]
            action = str(data.get("action", ""))[:200]
            self._pending_approval_id = approval_id
            self._chat_view.add_message(
                f"Action needed: {action}\n{description}\n\nType 'yes' to approve or 'no' to cancel.",
                is_assistant=True,
            )
            return

        # Handle live transcript from voice pipeline
        if msg_type == "transcript":
            transcript_text = data.get("text", "")
            if transcript_text:
                self._voice_view.add_transcript_line("don", transcript_text)
                self._voice_view.set_status("thinking")
                self._status_label.setText("Processing...")
                self._status_label.setStyleSheet(f"color: {ASSISTANT_COLOR}; font-size: 13px; background: transparent;")
            return

        # Handle speaker verification result
        if msg_type == "speaker_verified":
            is_owner = data.get("is_owner", False)
            if not is_owner:
                self._voice_view.set_status("idle")
                logger.debug("Desktop: speaker not verified — ignoring audio")
            return

        # Handle proactive messages (daily interview, morning/evening check-ins)
        if msg_type == "proactive":
            proactive_text = data.get("text", data.get("message", ""))
            if proactive_text:
                self._chat_view.add_message(proactive_text, is_assistant=True)
            return

        # Handle avatar stream URL
        if msg_type == "avatar_stream" and data.get("available"):
            url = data.get("url", "")
            if url:
                self._video_view.set_stream_url(url)
                self._video_btn.setEnabled(True)
                logger.info(f"Desktop: avatar stream available at {url}")
            return

        text = data.get("text", "")
        is_interim = data.get("is_interim", False)

        if not text:
            return

        if is_interim:
            self._chat_view.add_message(text, is_assistant=True, is_interim=True)
            self._voice_view.set_status("thinking")
        else:
            self._chat_view.remove_interim_messages()
            self._chat_view.add_message(text, is_assistant=True)
            self._voice_view.add_transcript_line("aether", text)
            self._voice_view.set_status("idle")
            # Reset status after final response
            self._status_label.setText("Connected")
            self._status_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 13px; background: transparent;")

    def _on_send_message(self, text: str) -> None:
        # Check if this is an approval response
        pending = self._pending_approval_id
        if pending:
            normalized = text.lower().strip().rstrip(".,!")
            if normalized in ("yes", "yeah", "sure", "go ahead", "do it", "ok", "confirm"):
                self._ws.send_approval_response(pending, True)
                self._pending_approval_id = None
                return
            if normalized in ("no", "nope", "cancel", "stop", "don't", "abort"):
                self._ws.send_approval_response(pending, False)
                self._pending_approval_id = None
                return
            # Non-matching input clears the pending approval so normal conversation resumes
            logger.info(f"Desktop: approval {pending} dismissed — user sent unrelated message")
            self._pending_approval_id = None

        self._ws.send_message(text)
        self._voice_view.add_transcript_line("don", text)

    def closeEvent(self, event) -> None:
        """Hide to tray instead of quitting (if tray is available)."""
        if self._tray and not self._force_quit:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "Aether",
                "Minimized to system tray. Double-click to restore.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            # No tray available or force quit — actually close
            self._video_view.stop()
            self._ws.disconnect_from_server()
            super().closeEvent(event)
