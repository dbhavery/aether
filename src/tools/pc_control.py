"""PC control tools — window management, keyboard, screenshots.

SECURITY: PyAutoGUI is only imported as a fallback inside take_screenshot().
Primary automation uses pywinauto (UIA backend) for window management.
All applications go through the allowlist. No arbitrary command execution.
"""

import asyncio
from pathlib import Path

from loguru import logger

from src.shared.config import get_settings, get_yaml_config

# Expanded allowlist (27 apps from v13 spec)
ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "chrome": "chrome.exe",
    "code": "code.exe",
    "terminal": "wt.exe",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "slack": "slack.exe",
    "teams": "ms-teams.exe",
    "outlook": "outlook.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "onenote": "onenote.exe",
    "paint": "mspaint.exe",
    "snip": "snippingtool.exe",
    "settings": "ms-settings:",
    "taskmanager": "taskmgr.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "obs": "obs64.exe",
    "vlc": "vlc.exe",
    "steam": "steam.exe",
    "blender": "blender.exe",
    "gimp": "gimp-2.10.exe",
    "audacity": "audacity.exe",
}


def _get_allowed_apps() -> dict[str, str]:
    """Get allowed apps from config, falling back to built-in list."""
    config = get_yaml_config()
    config_apps = config.get("permissions", {}).get("allowed_apps", [])
    if config_apps:
        # Config just has names — match against ALLOWED_APPS
        return {name: exe for name, exe in ALLOWED_APPS.items() if name in config_apps}
    return ALLOWED_APPS


async def open_application(app_name: str) -> dict:
    """Open an application by name. Only allowlisted applications are permitted."""
    try:
        allowed = _get_allowed_apps()
        executable = allowed.get(app_name.lower())
        if executable is None:
            logger.warning(f"Tools: blocked attempt to open non-allowlisted app '{app_name}'")
            return {
                "success": False,
                "error": f"Application '{app_name}' not in allowlist. Allowed: {', '.join(sorted(allowed.keys()))}",
            }

        # ms-settings: is a URI, not an executable
        if executable.startswith("ms-"):
            proc = await asyncio.create_subprocess_exec(
                "cmd",
                "/c",
                "start",
                executable,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                executable,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        logger.info(f"Tools: opened application '{executable}' (pid={proc.pid})")
        return {"success": True, "app": executable, "pid": proc.pid}
    except Exception as e:
        logger.error(f"Tools: failed to open '{app_name}': {e}")
        return {"success": False, "error": str(e)}


async def type_text(text: str, interval: float = 0.02) -> dict:
    """Type text using the keyboard via pywinauto."""
    try:
        from pywinauto.keyboard import send_keys

        # Escape special characters for pywinauto — single-pass to avoid
        # re-processing already-escaped sequences (e.g. "{+}" → "{{{+}}}")
        _PYWINAUTO_SPECIALS = {
            "{": "{{}",
            "}": "{}}",
            "+": "{+}",
            "^": "{^}",
            "%": "{%}",
            "~": "{~}",
            "(": "{(}",
            ")": "{)}",
        }
        safe_text = "".join(_PYWINAUTO_SPECIALS.get(c, c) for c in text)
        await asyncio.to_thread(send_keys, safe_text, pause=interval)
        logger.info(f"Tools: typed {len(text)} characters")
        return {"success": True, "chars_typed": len(text)}
    except Exception as e:
        logger.error(f"Tools: type_text error: {e}")
        return {"success": False, "error": str(e)}


async def get_clipboard() -> dict:
    """Get current clipboard contents."""
    try:
        import win32clipboard

        def _read_clipboard():
            win32clipboard.OpenClipboard()
            try:
                return win32clipboard.GetClipboardData()
            finally:
                win32clipboard.CloseClipboard()

        data = await asyncio.to_thread(_read_clipboard)
        return {"success": True, "content": data}
    except Exception as e:
        logger.error(f"Tools: get_clipboard error: {e}")
        return {"success": False, "error": str(e)}


_screenshot_dir: Path | None = None


def _get_screenshot_dir() -> Path:
    """Lazily resolve screenshot directory — avoids calling get_settings() at import time."""
    global _screenshot_dir
    if _screenshot_dir is None:
        _screenshot_dir = Path(get_settings().aether_data_path) / "screenshots"
    return _screenshot_dir


async def take_screenshot(save_path: str | None = None) -> dict:
    """Take a screenshot of the primary monitor using mss (faster than pyautogui)."""
    import tempfile

    screenshot_dir = _get_screenshot_dir()
    # Validate path BEFORE taking screenshot
    if save_path:
        resolved = Path(save_path).resolve()
        allowed = screenshot_dir.resolve()
        if not resolved.is_relative_to(allowed):
            logger.warning(f"Tools: blocked screenshot path outside allowed dir: {save_path}")
            return {"success": False, "error": f"save_path must be under {screenshot_dir}"}
        resolved.parent.mkdir(parents=True, exist_ok=True)
        path = str(resolved)
    else:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(suffix=".png", dir=str(screenshot_dir))
        import os

        os.close(fd)

    try:
        import mss

        def _capture():
            with mss.mss() as sct:
                sct.shot(output=path)

        await asyncio.to_thread(_capture)
        logger.info(f"Tools: screenshot saved to {path}")
        return {"success": True, "path": path}
    except ImportError:
        # Fallback to pyautogui if mss not available
        try:
            import pyautogui

            screenshot = await asyncio.to_thread(pyautogui.screenshot)
            screenshot.save(path)
            logger.info(f"Tools: screenshot saved (pyautogui fallback) to {path}")
            return {"success": True, "path": path}
        except Exception as e2:
            return {"success": False, "error": f"Screenshot capture failed: {e2}"}
    except Exception as e:
        logger.error(f"Tools: screenshot error: {e}")
        return {"success": False, "error": str(e)}


async def list_running_apps() -> dict:
    """List currently running applications."""
    try:
        import psutil

        def _list_procs():
            apps = []
            for proc in psutil.process_iter(["pid", "name", "status"]):
                try:
                    if proc.info["status"] == "running":
                        apps.append({"pid": proc.info["pid"], "name": proc.info["name"]})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return apps[:50]

        apps = await asyncio.to_thread(_list_procs)
        return {"success": True, "apps": apps}
    except Exception as e:
        logger.error(f"Tools: list_apps error: {e}")
        return {"success": False, "error": str(e)}


async def focus_window(title: str) -> dict:
    """Focus a window by its title (partial match)."""
    try:
        from pywinauto import Desktop

        def _focus():
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                if title.lower() in win.window_text().lower():
                    win.set_focus()
                    return {"success": True, "window": win.window_text()}
            return {"success": False, "error": f"No window matching '{title}' found"}

        return await asyncio.to_thread(_focus)
    except Exception as e:
        logger.error(f"Tools: focus_window error: {e}")
        return {"success": False, "error": str(e)}


async def get_active_window_title() -> dict:
    """Get the title of the currently active (foreground) window."""
    try:
        import ctypes

        def _get_foreground_title():
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value

        title = await asyncio.to_thread(_get_foreground_title)
        return {"success": True, "title": title}
    except Exception as e:
        logger.error(f"Tools: get_active_window error: {e}")
        return {"success": False, "error": str(e)}


async def minimize_window(title: str) -> dict:
    """Minimize a window by its title (partial match)."""
    try:
        from pywinauto import Desktop

        def _minimize():
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                if title.lower() in win.window_text().lower():
                    win.minimize()
                    return {"success": True, "window": win.window_text()}
            return {"success": False, "error": f"No window matching '{title}' found"}

        result = await asyncio.to_thread(_minimize)
        if result["success"]:
            logger.info(f"Tools: minimized window '{result['window']}'")
        return result
    except Exception as e:
        logger.error(f"Tools: minimize_window error: {e}")
        return {"success": False, "error": str(e)}


async def maximize_window(title: str) -> dict:
    """Maximize a window by its title (partial match)."""
    try:
        from pywinauto import Desktop

        def _maximize():
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                if title.lower() in win.window_text().lower():
                    win.maximize()
                    return {"success": True, "window": win.window_text()}
            return {"success": False, "error": f"No window matching '{title}' found"}

        result = await asyncio.to_thread(_maximize)
        if result["success"]:
            logger.info(f"Tools: maximized window '{result['window']}'")
        return result
    except Exception as e:
        logger.error(f"Tools: maximize_window error: {e}")
        return {"success": False, "error": str(e)}


async def close_window(title: str) -> dict:
    """Close a window by its title (partial match). May lose unsaved work."""
    try:
        from pywinauto import Desktop

        def _close():
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                if title.lower() in win.window_text().lower():
                    window_name = win.window_text()
                    win.close()
                    return {"success": True, "window": window_name}
            return {"success": False, "error": f"No window matching '{title}' found"}

        result = await asyncio.to_thread(_close)
        if result["success"]:
            logger.info(f"Tools: closed window '{result['window']}'")
        return result
    except Exception as e:
        logger.error(f"Tools: close_window error: {e}")
        return {"success": False, "error": str(e)}
