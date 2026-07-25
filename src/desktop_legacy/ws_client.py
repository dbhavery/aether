"""WebSocket client — connects to Core server, handles send/receive."""

import json
from datetime import UTC, datetime

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWebSockets import QWebSocket

from src.core.auth import get_token_for_client


class WebSocketClient(QObject):
    """Connects to Aether Core WebSocket server."""

    connected = Signal()
    disconnected = Signal()
    message_received = Signal(dict)  # {"text": str, "emotion": str, ...}
    error_occurred = Signal(str)

    def __init__(self, url: str = "ws://localhost:8765", parent=None):
        super().__init__(parent)
        self._base_url = url
        self._socket = QWebSocket()
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.textMessageReceived.connect(self._on_message)
        self._socket.errorOccurred.connect(self._on_error)
        self._reconnect_timer_id = None
        self._is_connected = False
        self._intentional_disconnect = False

        # Heartbeat timer — sends ping every 30s while connected
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(30000)
        self._heartbeat_timer.timeout.connect(self.send_ping)

    def connect_to_server(self) -> None:
        self._intentional_disconnect = False
        if self._is_connected:
            return
        # Prevent overlapping connection attempts (previous open() still in progress)
        from PySide6.QtNetwork import QAbstractSocket

        if self._socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            return
        # Re-fetch token on every connect attempt (handles server token rotation)
        try:
            token = get_token_for_client()
        except Exception as e:
            logger.warning(f"Desktop: token fetch failed ({e}) — connecting without auth")
            token = None
        if token:
            separator = "&" if "?" in self._base_url else "?"
            url = f"{self._base_url}{separator}token={token}"
        else:
            url = self._base_url
        logger.info(f"Desktop: connecting to {self._base_url}")
        from PySide6.QtCore import QUrl

        self._socket.open(QUrl(url))

    def disconnect_from_server(self) -> None:
        self._intentional_disconnect = True
        if self._reconnect_timer_id is not None:
            self.killTimer(self._reconnect_timer_id)
            self._reconnect_timer_id = None
        self._socket.close()

    def send_message(self, text: str) -> None:
        if not self._is_connected:
            self.error_occurred.emit("Not connected to server")
            return
        msg = {
            "type": "user_message",
            "text": text,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._socket.sendTextMessage(json.dumps(msg))

    def send_approval_response(self, approval_id: str, approved: bool) -> None:
        """Send an approval/rejection response to the server."""
        if not self._is_connected:
            self.error_occurred.emit("Not connected to server")
            return
        msg = {
            "type": "approval_response",
            "approval_id": approval_id,
            "approved": approved,
        }
        self._socket.sendTextMessage(json.dumps(msg))
        logger.info(f"Desktop: sent approval response {approval_id} -> {'approved' if approved else 'rejected'}")

    def send_json(self, data: dict) -> None:
        """Send an arbitrary JSON message to the server."""
        if not self._is_connected:
            self.error_occurred.emit("Not connected to server")
            return
        self._socket.sendTextMessage(json.dumps(data))

    def send_ping(self) -> None:
        if self._is_connected:
            self._socket.sendTextMessage(json.dumps({"type": "ping"}))

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def _on_connected(self) -> None:
        logger.info("Desktop: WebSocket connected")
        self._is_connected = True
        if self._reconnect_timer_id is not None:
            self.killTimer(self._reconnect_timer_id)
            self._reconnect_timer_id = None
        self._heartbeat_timer.start()
        self.connected.emit()

    def _on_disconnected(self) -> None:
        logger.warning("Desktop: WebSocket disconnected")
        self._is_connected = False
        self._heartbeat_timer.stop()
        self.disconnected.emit()
        # Auto-reconnect after 3 seconds — but NOT if disconnect was intentional
        if not self._intentional_disconnect and self._reconnect_timer_id is None:
            self._reconnect_timer_id = self.startTimer(3000)

    def timerEvent(self, event) -> None:
        if event.timerId() == self._reconnect_timer_id:
            self.connect_to_server()

    def _on_error(self, error) -> None:
        error_msg = self._socket.errorString()
        logger.warning(f"Desktop: WebSocket error: {error_msg}")
        self.error_occurred.emit(error_msg)

    def _on_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
            msg_type = data.get("type", "")
            if msg_type == "pong":
                return  # Heartbeat response, ignore
            if msg_type == "response":
                self.message_received.emit(data)
            elif msg_type == "wake_word":
                self.message_received.emit({"type": "wake_word", "listening": True})
            elif msg_type in (
                "avatar_stream",
                "proactive",
                "error",
                "approval_request",
                "transcript",
                "speaker_verified",
            ):
                self.message_received.emit(data)
            else:
                logger.debug(f"Desktop: unhandled message type: {msg_type}")
        except json.JSONDecodeError:
            logger.warning(f"Desktop: invalid JSON received: {raw[:100]}")
