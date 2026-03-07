"""Desktop app entry point — launches the Aether GUI with system tray."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

if TYPE_CHECKING:
    from src.desktop.main_window import MainWindow

ICON_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "branding" / "aether.ico"


def launch_desktop() -> None:
    """Launch the Aether desktop client with system tray icon."""
    logger.info("Desktop: launching GUI")
    app = QApplication(sys.argv)
    app.setApplicationName("Aether")
    app.setQuitOnLastWindowClosed(False)  # Keep running when window is hidden

    # Load icon
    icon = QIcon()
    if ICON_PATH.exists():
        icon = QIcon(str(ICON_PATH))
        app.setWindowIcon(icon)
        logger.info(f"Desktop: loaded icon from {ICON_PATH}")
    else:
        logger.warning(f"Desktop: icon not found at {ICON_PATH}")

    from src.desktop.main_window import MainWindow

    window = MainWindow()

    # System tray
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(icon, app)

        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show")
        show_action.triggered.connect(window.show_from_tray)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(window.quit_application)

        tray.setContextMenu(tray_menu)
        tray.setToolTip("Aether")
        tray.activated.connect(lambda reason: _on_tray_activated(reason, window))
        tray.show()

        # Give the window a reference to the tray so it knows tray is available
        window.set_tray_icon(tray)
        logger.info("Desktop: system tray icon active")
    else:
        logger.warning("Desktop: system tray not available — close will quit")

    window.show()
    sys.exit(app.exec())


def _on_tray_activated(reason: QSystemTrayIcon.ActivationReason, window: MainWindow) -> None:
    """Handle tray icon clicks — single-click or double-click to show window."""
    if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
        window.show_from_tray()


if __name__ == "__main__":
    launch_desktop()
