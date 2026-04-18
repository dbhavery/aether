"""API Keys settings tab — manage external service credentials.

Groups services by category with status badges, masked key inputs,
save/clear/test buttons, and a "Test all" action at the bottom.
"""

from __future__ import annotations

import asyncio
import webbrowser
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QObject, Qt, Signal
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

if TYPE_CHECKING:
    from collections.abc import Callable

from src.desktop.settings_widgets import COLORS
from src.desktop.theme import ACCENT, COLOR_ERROR, COLOR_SUCCESS, COLOR_WARNING
from src.shared.api_registry import (
    AuthMethod,
    ServiceCategory,
    ServiceDefinition,
    get_service_status,
    get_services_by_category,
)
from src.shared.key_store import delete_key, get_key, mask_key, set_key

# ---------------------------------------------------------------------------
# Status badge colors — derived from theme tokens
# ---------------------------------------------------------------------------

_STATUS_COLORS = {
    "configured": COLOR_SUCCESS,
    "missing": COLOR_ERROR,
    "gateway": ACCENT,
    "testing": COLOR_WARNING,
    "passed": COLOR_SUCCESS,
    "failed": COLOR_ERROR,
}


# ---------------------------------------------------------------------------
# QThread-based async test runner
# ---------------------------------------------------------------------------


class _TestWorker(QObject):
    """Runs a service test_fn in a background QThread."""

    finished = Signal(str, bool, str)  # service_name, success, message

    def __init__(self, service_name: str, test_fn: Callable[[], tuple[bool, str]]) -> None:
        super().__init__()
        self._service_name = service_name
        self._test_fn = test_fn

    def run(self) -> None:
        """Execute the test function (may be sync or async)."""
        try:
            result = self._test_fn()
            # Handle coroutine-returning test functions
            if asyncio.iscoroutine(result):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(result)
                finally:
                    loop.close()
            success, message = result
        except Exception as exc:
            logger.error(f"Test failed for {self._service_name}: {exc}")
            success = False
            message = f"Error: {exc}"
        self.finished.emit(self._service_name, success, message)


# ---------------------------------------------------------------------------
# Per-service row widget
# ---------------------------------------------------------------------------


class _ServiceRow(QWidget):
    """One row in the API keys tab representing a single service."""

    test_requested = Signal(str)  # service_name

    def __init__(self, svc: ServiceDefinition, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._svc = svc
        self._revealed = False
        self._setup_ui()
        self._refresh_status()

    # ── UI construction ──────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            _ServiceRow {{
                background: {COLORS["card"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 8px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        # -- Top row: name + badge + description
        top = QHBoxLayout()
        top.setSpacing(8)

        name_label = QLabel(self._svc.display_name)
        name_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: bold;")
        top.addWidget(name_label)

        self._badge = QLabel()
        self._badge.setFixedHeight(20)
        self._badge.setStyleSheet("padding: 2px 8px; border-radius: 4px; font-size: 11px;")
        top.addWidget(self._badge)

        top.addStretch()

        # "Get key" link (only if docs_url exists)
        if self._svc.docs_url:
            link_btn = QPushButton("Get key →")
            link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            link_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {COLORS["accent"]};
                    border: none;
                    font-size: 12px;
                    text-decoration: underline;
                }}
                QPushButton:hover {{ color: #3399FF; }}
            """)
            link_btn.clicked.connect(lambda: webbrowser.open(self._svc.docs_url))
            top.addWidget(link_btn)

        outer.addLayout(top)

        # -- Description
        if self._svc.description:
            desc = QLabel(self._svc.description)
            desc.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
            desc.setWordWrap(True)
            outer.addWidget(desc)

        # -- Key input row (API_KEY services only)
        if self._svc.auth_method == AuthMethod.API_KEY:
            key_row = QHBoxLayout()
            key_row.setSpacing(6)

            self._key_input = QLineEdit()
            self._key_input.setPlaceholderText("Paste API key here…")
            self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._key_input.setStyleSheet(f"""
                QLineEdit {{
                    background: {COLORS["input"]};
                    color: {COLORS["text"]};
                    border: 1px solid {COLORS["border"]};
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 13px;
                    font-family: "Consolas", monospace;
                }}
                QLineEdit:focus {{ border-color: {COLORS["accent"]}; }}
            """)
            key_row.addWidget(self._key_input, stretch=1)

            # Show/Hide toggle
            self._toggle_btn = QPushButton("Show")
            self._toggle_btn.setFixedWidth(50)
            self._toggle_btn.setStyleSheet(self._small_btn_qss())
            self._toggle_btn.clicked.connect(self._toggle_visibility)
            key_row.addWidget(self._toggle_btn)

            # Save button
            save_btn = QPushButton("Save")
            save_btn.setFixedWidth(50)
            save_btn.setStyleSheet(self._small_btn_qss(accent=True))
            save_btn.clicked.connect(self._save_key)
            key_row.addWidget(save_btn)

            # Clear button
            clear_btn = QPushButton("Clear")
            clear_btn.setFixedWidth(50)
            clear_btn.setStyleSheet(self._small_btn_qss(danger=True))
            clear_btn.clicked.connect(self._clear_key)
            key_row.addWidget(clear_btn)

            outer.addLayout(key_row)

            # Masked display
            self._masked_label = QLabel()
            self._masked_label.setStyleSheet(
                f"color: {COLORS['text_dim']}; font-size: 11px; font-family: 'Consolas', monospace;"
            )
            outer.addWidget(self._masked_label)
        else:
            # GATEWAY / OAUTH — no input field
            self._key_input = None
            self._masked_label = None

        # -- Bottom row: Test button + status message
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        if self._svc.auth_method == AuthMethod.API_KEY and self._svc.test_fn is not None:
            self._test_btn = QPushButton("Test connection")
            self._test_btn.setFixedWidth(120)
            self._test_btn.setStyleSheet(self._small_btn_qss())
            self._test_btn.clicked.connect(self._request_test)
            bottom.addWidget(self._test_btn)
        else:
            self._test_btn = None

        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        self._status_label.setWordWrap(True)
        bottom.addWidget(self._status_label, stretch=1)

        outer.addLayout(bottom)

    # ── Actions ──────────────────────────────────────────────────

    def _toggle_visibility(self) -> None:
        if self._key_input is None:
            return
        self._revealed = not self._revealed
        if self._revealed:
            self._key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_btn.setText("Hide")
        else:
            self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_btn.setText("Show")

    def _save_key(self) -> None:
        if self._key_input is None:
            return
        value = self._key_input.text().strip()
        if not value:
            self._status_label.setText("Cannot save empty key.")
            self._status_label.setStyleSheet(f"color: {_STATUS_COLORS['failed']}; font-size: 12px;")
            return
        try:
            set_key(self._svc.env_var, value)
            self._key_input.clear()
            self._status_label.setText("Key saved.")
            self._status_label.setStyleSheet(f"color: {_STATUS_COLORS['configured']}; font-size: 12px;")
            self._refresh_status()
        except (ValueError, OSError) as exc:
            logger.error(f"Failed to save key for {self._svc.name}: {exc}")
            self._status_label.setText(f"Save failed: {exc}")
            self._status_label.setStyleSheet(f"color: {_STATUS_COLORS['failed']}; font-size: 12px;")

    def _clear_key(self) -> None:
        try:
            removed = delete_key(self._svc.env_var)
            if removed:
                self._status_label.setText("Key removed.")
            else:
                self._status_label.setText("No key was set.")
            self._status_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
            self._refresh_status()
        except OSError as exc:
            logger.error(f"Failed to clear key for {self._svc.name}: {exc}")
            self._status_label.setText(f"Clear failed: {exc}")
            self._status_label.setStyleSheet(f"color: {_STATUS_COLORS['failed']}; font-size: 12px;")

    def _request_test(self) -> None:
        self.test_requested.emit(self._svc.name)

    # ── Status refresh ───────────────────────────────────────────

    def _refresh_status(self) -> None:
        """Update badge and masked label from current key state."""
        if self._svc.auth_method == AuthMethod.GATEWAY:
            self._set_badge("Via gateway", _STATUS_COLORS["gateway"])
            self._status_label.setText("Routed through OpenClaw — no key needed.")
            return

        raw = get_key(self._svc.env_var)
        if raw:
            self._set_badge("Configured", _STATUS_COLORS["configured"])
            if self._masked_label is not None:
                self._masked_label.setText(f"Current: {mask_key(raw)}")
        else:
            self._set_badge("Not set", _STATUS_COLORS["missing"])
            if self._masked_label is not None:
                self._masked_label.setText(mask_key(None))

    def _set_badge(self, text: str, color: str) -> None:
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"background: {color}; color: white; padding: 2px 8px; "
            f"border-radius: 4px; font-size: 11px; font-weight: bold;"
        )

    def set_test_result(self, success: bool, message: str) -> None:
        """Called externally after a test completes."""
        if success:
            self._set_badge("Connected", _STATUS_COLORS["passed"])
            self._status_label.setText(message or "Test passed.")
            self._status_label.setStyleSheet(f"color: {_STATUS_COLORS['passed']}; font-size: 12px;")
        else:
            self._set_badge("Failed", _STATUS_COLORS["failed"])
            self._status_label.setText(message or "Test failed.")
            self._status_label.setStyleSheet(f"color: {_STATUS_COLORS['failed']}; font-size: 12px;")
        if self._test_btn is not None:
            self._test_btn.setEnabled(True)
            self._test_btn.setText("Test connection")

    def set_testing(self) -> None:
        """Visual feedback while a test is running."""
        self._set_badge("Testing…", _STATUS_COLORS["testing"])
        self._status_label.setText("Running connection test…")
        self._status_label.setStyleSheet(f"color: {_STATUS_COLORS['testing']}; font-size: 12px;")
        if self._test_btn is not None:
            self._test_btn.setEnabled(False)
            self._test_btn.setText("Testing…")

    # ── QSS helpers ──────────────────────────────────────────────

    @staticmethod
    def _small_btn_qss(*, accent: bool = False, danger: bool = False) -> str:
        if accent:
            bg, hover, pressed = COLORS["accent"], "#0055CC", "#003388"
        elif danger:
            bg, hover, pressed = "#8B0000", "#AA0000", "#660000"
        else:
            bg, hover, pressed = COLORS["input"], COLORS["border"], COLORS["card"]
        return f"""
            QPushButton {{
                background: {bg}; color: {COLORS["text"]};
                border: 1px solid {COLORS["border"]}; border-radius: 4px;
                padding: 4px 8px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {pressed}; }}
            QPushButton:disabled {{ background: {COLORS["card"]}; color: {COLORS["text_dim"]}; }}
        """


# ---------------------------------------------------------------------------
# Main tab widget
# ---------------------------------------------------------------------------


class ApiKeysTab(QWidget):
    """Full API Keys settings tab — groups services by category."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, _ServiceRow] = {}
        self._workers: list[_TestWorker] = []  # prevent GC of workers
        self._threads: list[object] = []  # prevent GC of threads
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {COLORS["bg"]}; border: none; }}
        """)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        title = QLabel("API Keys & Services")
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel("Manage credentials for external services. Gateway services are auto-routed.")
        subtitle.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Add a separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {COLORS['border']};")
        layout.addWidget(sep)

        # Build category sections
        for category in ServiceCategory:
            services = get_services_by_category(category)
            if not services:
                continue
            self._add_category_section(layout, category, services)

        layout.addStretch()

        # "Test all" button at the bottom
        test_all_row = QHBoxLayout()
        test_all_row.addStretch()
        test_all_btn = QPushButton("Test all services")
        test_all_btn.setFixedWidth(160)
        test_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS["accent"]}; color: {COLORS["text"]};
                border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #0055CC; }}
            QPushButton:pressed {{ background: #003388; }}
        """)
        test_all_btn.clicked.connect(self._test_all)
        test_all_row.addWidget(test_all_btn)
        test_all_row.addStretch()
        layout.addLayout(test_all_row)

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _add_category_section(
        self,
        parent_layout: QVBoxLayout,
        category: ServiceCategory,
        services: list[ServiceDefinition],
    ) -> None:
        """Add a category header and its service rows."""
        # Category header
        header = QLabel(category.value)
        header.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 15px; font-weight: bold; margin-top: 12px; margin-bottom: 4px;"
        )
        parent_layout.addWidget(header)

        for svc in services:
            row = _ServiceRow(svc)
            row.test_requested.connect(self._run_single_test)
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            parent_layout.addWidget(row)
            self._rows[svc.name] = row

    # ── Test execution ───────────────────────────────────────────

    def _run_single_test(self, service_name: str) -> None:
        """Run the test_fn for one service in a background QThread."""
        from PySide6.QtCore import QThread

        status = get_service_status(service_name)
        if status is None:
            logger.warning(f"Cannot test unknown service: {service_name}")
            return

        row = self._rows.get(service_name)
        if row is None:
            return

        # Find the service definition to get its test_fn
        from src.shared.api_registry import get_service

        svc = get_service(service_name)
        if svc is None or svc.test_fn is None:
            row.set_test_result(False, "No test function defined for this service.")
            return

        if not status.key_present:
            row.set_test_result(False, "No key configured — set the key first.")
            return

        row.set_testing()

        thread = QThread()
        worker = _TestWorker(service_name, svc.test_fn)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(lambda name, ok, msg: self._on_test_done(name, ok, msg))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Prevent garbage collection
        self._workers.append(worker)
        self._threads.append(thread)

        thread.start()

    def _on_test_done(self, service_name: str, success: bool, message: str) -> None:
        """Handle test completion — update the row UI and clean up finished workers/threads."""
        row = self._rows.get(service_name)
        if row is not None:
            row.set_test_result(success, message)
        logger.info(f"Test {service_name}: {'PASS' if success else 'FAIL'} — {message}")

        # Prune finished workers and threads to prevent unbounded memory growth
        self._workers = [w for w in self._workers if not getattr(w, "_deleted", False)]
        self._threads = [t for t in self._threads if t.isRunning()]

    def _test_all(self) -> None:
        """Sequentially launch tests for every service that has a test_fn + key."""
        from src.shared.api_registry import all_services

        for svc in all_services():
            if svc.test_fn is not None and svc.auth_method == AuthMethod.API_KEY:
                status = get_service_status(svc.name)
                if status is not None and status.key_present:
                    self._run_single_test(svc.name)
