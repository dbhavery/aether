"""JS <-> Python bridge exposed via pywebview ``window.pywebview.api``.

Every public method on ``DesktopBridge`` is reachable from the frontend as
``window.pywebview.api.<method>(...)``. Keep the surface small and stable —
the frontend links against it by name.
"""

from __future__ import annotations

import json
import platform
import webbrowser
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from loguru import logger

# Version string is cheap to change; keep it in sync with pyproject.toml once
# one exists. The build tag is "dev" for non-packaged runs and gets stamped by
# the installer at packaging time.
_APP_VERSION = "1.0.0-dev"
_APP_BUILD = "dev"

# Health endpoint exposes /auth/token which mints the short-lived WS token.
# We reuse it here rather than touching the keyring directly so there is a
# single auth code path and a single rate-limit.
_HEALTH_BASE = "http://127.0.0.1:8767"


class DesktopBridge:
    """Python API surface attached to the pywebview window.

    The class is instantiated in ``desktop.main``. After the window is built,
    ``attach_window`` is called so methods that need the webview handle
    (native dialogs) can reach it.
    """

    def __init__(self) -> None:
        self._window: Any = None

    def attach_window(self, window: Any) -> None:
        """Store the pywebview window handle so dialog methods can reach it."""
        self._window = window

    # ------------------------------------------------------------------ dialogs

    def open_file_dialog(self, options: dict[str, Any] | None = None) -> list[str] | None:
        """Open a native file picker.

        ``options``:
            - ``dialog_type``: ``"open"`` (default) or ``"save"``
            - ``directory``: starting directory as a string
            - ``allow_multiple``: bool, open dialog only
            - ``file_types``: list of filter strings, e.g.
              ``["Image Files (*.png;*.jpg)", "All Files (*.*)"]``

        Returns a list of selected paths, or ``None`` if the user cancelled or
        the window is not ready.
        """
        import webview

        if self._window is None:
            logger.warning("bridge: open_file_dialog called before window attached")
            return None

        opts = options or {}
        dialog_type = opts.get("dialog_type", "open")
        directory = opts.get("directory", "")
        allow_multiple = bool(opts.get("allow_multiple", False))
        file_types = tuple(opts.get("file_types") or ())

        try:
            if dialog_type == "save":
                result = self._window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    directory=directory,
                    file_types=file_types,
                )
            else:
                result = self._window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    directory=directory,
                    allow_multiple=allow_multiple,
                    file_types=file_types,
                )
        except Exception as exc:
            logger.warning(f"bridge: open_file_dialog error: {exc!r}")
            return None

        if result is None:
            return None
        return list(result)

    # --------------------------------------------------------------- auth token

    def get_keyring_token(self) -> str | None:
        """Return a short-lived WS auth token from the backend.

        The backend's health server exposes ``/auth/token`` and handles both
        keyring lookup and rate limiting. We proxy to it rather than touching
        the keyring directly.
        """
        try:
            with urlopen(f"{_HEALTH_BASE}/auth/token", timeout=2.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("token")
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            logger.warning(f"bridge: get_keyring_token failed: {exc!r}")
            return None

    # ------------------------------------------------------------- external url

    def open_external(self, url: str) -> bool:
        """Open ``url`` in the user's default browser. Returns True on success."""
        if not url:
            return False
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:")):
            # Refuse local-file or arbitrary-scheme URLs so a malicious page
            # loaded in the webview cannot escalate to launching local files.
            logger.warning(f"bridge: open_external refused non-web URL: {url!r}")
            return False
        try:
            return bool(webbrowser.open(url, new=2))
        except Exception as exc:
            logger.warning(f"bridge: open_external({url!r}) failed: {exc!r}")
            return False

    # -------------------------------------------------------------- app info

    def get_app_info(self) -> dict[str, Any]:
        """Return ``{version, build, platform, data_dir}`` for About panels."""
        data_dir = ""
        try:
            from src.shared.paths import get_data_dir

            data_dir = str(get_data_dir())
        except Exception as exc:
            logger.debug(f"bridge: get_data_dir unavailable: {exc!r}")

        return {
            "version": _APP_VERSION,
            "build": _APP_BUILD,
            "platform": platform.system().lower(),
            "data_dir": data_dir,
        }


__all__ = ["DesktopBridge"]
