"""Video view — renders the LivePortrait MJPEG stream as Aether's face."""

import contextlib
import threading
import urllib.request
from urllib.parse import urlparse

from loguru import logger
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from src.desktop.theme import BG_PIT, TEXT_FAINT


class MJPEGWorker(QObject):
    """Reads MJPEG stream in a background thread and emits frames as signals."""

    frame_ready = Signal(bytes)
    stream_error = Signal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url
        self._running = False
        self._emit_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start_stream(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop_stream(self) -> None:
        with self._emit_lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _read_loop(self) -> None:
        """Read MJPEG stream frame by frame."""
        max_buffer = 1024 * 1024  # 1MB cap to prevent OOM on corrupt streams
        try:
            with urllib.request.urlopen(self._url, timeout=5) as req:  # noqa: S310  # nosec B310  # URL from config
                buffer = bytearray()
                while self._running:
                    chunk = req.read(4096)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    # Find JPEG boundaries (SOI = 0xFFD8, EOI = 0xFFD9)
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9")
                    if start != -1 and end != -1 and end > start:
                        jpeg_bytes = bytes(buffer[start : end + 2])
                        buffer = buffer[end + 2 :]
                        with self._emit_lock:
                            if self._running:  # Guard: don't emit to destroyed QObject
                                self.frame_ready.emit(jpeg_bytes)
                    elif len(buffer) > max_buffer:
                        # Corrupted stream — discard and look for next SOI
                        logger.warning("VideoView: buffer exceeded 1MB, discarding")
                        buffer.clear()
        except Exception as e:
            if self._running:
                self.stream_error.emit(str(e))
                logger.warning(f"VideoView: stream error: {e}")


class VideoView(QWidget):
    """Widget that displays animated avatar from MJPEG stream."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: MJPEGWorker | None = None
        self._stream_url: str | None = None
        self._build_ui()

    def _cleanup_worker(self) -> None:
        """Stop and disconnect the current MJPEG worker."""
        if self._worker:
            self._worker.stop_stream()
            with contextlib.suppress(RuntimeError):
                self._worker.frame_ready.disconnect(self._on_frame)
            with contextlib.suppress(RuntimeError):
                self._worker.stream_error.disconnect(self._on_error)
            self._worker = None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._face_label = QLabel()
        self._face_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._face_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Face label container — BG_PIT (deepest recess), TEXT_FAINT, 15px
        self._face_label.setStyleSheet(f"background-color: {BG_PIT}; color: {TEXT_FAINT}; font-size: 15px;")
        self._face_label.setText("Avatar not connected")
        layout.addWidget(self._face_label)

    @staticmethod
    def _is_safe_stream_url(url: str) -> bool:
        """Validate MJPEG stream URL — only allow http/https to trusted hosts."""
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        # Allow localhost and Tailscale 100.x.x.x range
        if host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return True
        if host.startswith("100."):
            return True
        logger.warning(f"VideoView: blocked stream from untrusted host: {host}")
        return False

    def set_stream_url(self, url: str) -> None:
        """Start streaming from the given MJPEG URL."""
        if not self._is_safe_stream_url(url):
            self._face_label.setText("Avatar blocked\nUntrusted stream URL")
            return
        self._stream_url = url
        self._cleanup_worker()
        self._worker = MJPEGWorker(url)
        self._worker.frame_ready.connect(self._on_frame, Qt.ConnectionType.QueuedConnection)
        self._worker.stream_error.connect(self._on_error, Qt.ConnectionType.QueuedConnection)
        self._worker.start_stream()
        logger.info(f"VideoView: streaming from {url}")

    def _on_frame(self, jpeg_bytes: bytes) -> None:
        image = QImage.fromData(jpeg_bytes, "JPEG")
        if not image.isNull():
            pixmap = QPixmap.fromImage(image)
            scaled = pixmap.scaled(
                self._face_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._face_label.setPixmap(scaled)
            self._face_label.setStyleSheet(f"background-color: {BG_PIT};")

    def _on_error(self, error: str) -> None:
        self._face_label.setText(f"Avatar unavailable\n{error}")
        self._face_label.setStyleSheet(f"background-color: {BG_PIT}; color: {TEXT_FAINT}; font-size: 13px;")

    def pause_stream(self) -> None:
        """Pause the MJPEG stream when switching away from video mode."""
        self._cleanup_worker()
        logger.info("VideoView: stream paused")

    def resume_stream(self) -> None:
        """Resume the MJPEG stream when switching back to video mode."""
        if self._stream_url:
            self._cleanup_worker()
            self._worker = MJPEGWorker(self._stream_url)
            self._worker.frame_ready.connect(self._on_frame, Qt.ConnectionType.QueuedConnection)
            self._worker.stream_error.connect(self._on_error, Qt.ConnectionType.QueuedConnection)
            self._worker.start_stream()
            logger.info(f"VideoView: stream resumed from {self._stream_url}")

    def stop(self) -> None:
        """Stop the MJPEG stream reader."""
        self._cleanup_worker()
