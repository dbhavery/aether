"""Task panel — shows agent task status. Accessible via toolbar button."""

from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.desktop.theme import (
    ACCENT,
    BG_RAISED,
    BG_VOID,
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_WARNING,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

COLORS = {
    "bg": BG_VOID,
    "card": BG_RAISED,
    "text": TEXT_PRIMARY,
    "dim": TEXT_SECONDARY,
    "done": COLOR_SUCCESS,
    "running": ACCENT,
    "pending": COLOR_WARNING,
    "failed": COLOR_ERROR,
}

STATUS_COLORS = {
    "complete": COLORS["done"],
    "running": COLORS["running"],
    "pending": COLORS["pending"],
    "failed": COLORS["failed"],
}


class TaskPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._refresh)
        # Timer starts only when the panel becomes visible (see showEvent)

    def showEvent(self, event) -> None:
        """Start the refresh timer when the panel becomes visible."""
        super().showEvent(event)
        self._refresh()
        self._timer.start()

    def hideEvent(self, event) -> None:
        """Stop the refresh timer when the panel is hidden."""
        self._timer.stop()
        super().hideEvent(event)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QHBoxLayout()
        title = QLabel("Agent Tasks")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {COLORS['text']};")
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(28)
        refresh_btn.setStyleSheet(f"color: {COLORS['dim']}; background: transparent; border: none; font-size: 11px;")
        refresh_btn.clicked.connect(self._refresh)
        clear_btn = QPushButton("Clear done")
        clear_btn.setFixedHeight(28)
        clear_btn.setStyleSheet(f"color: {COLORS['dim']}; background: transparent; border: none; font-size: 11px;")
        clear_btn.clicked.connect(self._clear_done)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh_btn)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._task_layout = QVBoxLayout(self._container)
        self._task_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._task_layout.setSpacing(8)
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, stretch=1)

    def _refresh(self) -> None:
        """Fetch task list from agent registry and update UI."""
        try:
            from src.agents.task_registry import get_task_summary

            tasks = get_task_summary()
            self._update_tasks(tasks)
        except Exception:
            self._update_tasks([])

    def _update_tasks(self, tasks: list) -> None:
        # Clear existing widgets
        while self._task_layout.count():
            item = self._task_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not tasks:
            placeholder = QLabel("No active tasks")
            placeholder.setStyleSheet(f"color: {COLORS['dim']}; font-size: 12px;")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._task_layout.addWidget(placeholder)
            return

        for task in tasks:
            card = self._make_task_card(task)
            self._task_layout.addWidget(card)

    def _make_task_card(self, task: dict) -> QFrame:
        card = QFrame()
        status = task.get("status", "pending")
        status_color = STATUS_COLORS.get(status, COLORS["dim"])
        card.setStyleSheet(
            f"QFrame {{ background: {COLORS['card']}; border-radius: 6px; "
            f"padding: 8px; border-left: 3px solid {status_color}; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        agent_label = QLabel(task.get("agent", "unknown"))
        agent_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 11px; font-weight: bold;")
        status_label = QLabel(f"  {status.upper()}")
        status_label.setStyleSheet(f"color: {status_color}; font-size: 10px; font-weight: bold;")
        top_row.addWidget(agent_label)
        top_row.addStretch()
        top_row.addWidget(status_label)
        layout.addLayout(top_row)

        instruction = QLabel(task.get("instruction", "")[:100])
        instruction.setWordWrap(True)
        instruction.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px;")
        layout.addWidget(instruction)

        if task.get("result_preview"):
            result = QLabel(task["result_preview"])
            result.setWordWrap(True)
            result.setStyleSheet(f"color: {COLORS['dim']}; font-size: 11px;")
            layout.addWidget(result)

        if task.get("error"):
            error = QLabel(f"Error: {task['error']}")
            error.setWordWrap(True)
            error.setStyleSheet(f"color: {COLORS['failed']}; font-size: 11px;")
            layout.addWidget(error)

        # Retry button for failed tasks
        if status == "failed":
            retry_btn = QPushButton("Retry")
            retry_btn.setFixedHeight(24)
            retry_btn.setStyleSheet(
                f"color: {COLORS['text']}; background: {COLORS['failed']}; "
                f"border: none; border-radius: 4px; font-size: 10px; padding: 2px 8px;"
            )
            task_id = task.get("task_id", "")
            retry_btn.clicked.connect(lambda checked, tid=task_id: self._retry_task(tid))
            layout.addWidget(retry_btn, alignment=Qt.AlignmentFlag.AlignRight)

        return card

    def _retry_task(self, task_id: str) -> None:
        """Re-dispatch a failed task."""
        try:
            logger.info(f"TaskPanel: retry requested for task {task_id}")
            # For now, just log — full retry requires agent re-dispatch
            self._refresh()
        except Exception as e:
            logger.debug(f"TaskPanel: retry failed: {e}")

    def _clear_done(self) -> None:
        try:
            from src.agents.task_registry import clear_completed_tasks

            clear_completed_tasks()
            self._refresh()
        except Exception as e:
            logger.debug(f"TaskPanel: clear_done failed: {e}")
