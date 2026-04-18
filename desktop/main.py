"""Entry point for the Aether desktop shell.

Responsibilities:

1. **Backend supervision.** If port 8765 is already taken we assume a backend
   is running and attach to it. Otherwise we spawn ``python -m src.main`` as
   a subprocess and terminate it when the window closes.
2. **URL selection.** If the Next.js dev server answers on
   ``http://127.0.0.1:3000/`` within a 1 s probe, load that URL so UI work
   hot-reloads. Otherwise load the static export at
   ``frontend/out/index.html``.
3. **Window.** Dark-chrome pywebview window (1280x860, min 1024x720) with
   the JS bridge attached via ``js_api``.

Run: ``pythonw -m desktop.main`` (production, no console) or
``python -m desktop.main`` (dev, console for logs).
"""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import webview
from loguru import logger

from desktop.bridge import DesktopBridge

# -- filesystem layout ---------------------------------------------------------
# ``desktop/main.py`` is a child of the repo root, so ``parents[1]`` lands
# on the repo. ``frontend/out/`` is produced by ``next build``.
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
FRONTEND_OUT: Path = REPO_ROOT / "frontend" / "out"
FRONTEND_INDEX: Path = FRONTEND_OUT / "index.html"

# -- backend topology ----------------------------------------------------------
BACKEND_HOST: str = "127.0.0.1"
BACKEND_WS_PORT: int = 8765
BACKEND_HEALTH_PORT: int = 8767
DEV_URL: str = "http://127.0.0.1:3000/"

# -- timeouts ------------------------------------------------------------------
DEV_PROBE_TIMEOUT_S: float = 1.0
BACKEND_SPAWN_TIMEOUT_S: float = 15.0
BACKEND_POLL_INTERVAL_S: float = 0.3

# -- window chrome -------------------------------------------------------------
WINDOW_TITLE: str = "Aether"
WINDOW_SIZE: tuple[int, int] = (1280, 860)
WINDOW_MIN_SIZE: tuple[int, int] = (1024, 720)
WINDOW_BG: str = "#0B0B0F"


# -- backend subprocess handle (lifetime = process lifetime) ------------------
_backend_proc: subprocess.Popen[bytes] | None = None


def _port_in_use(host: str, port: int, timeout: float = 0.3) -> bool:
    """Return True if *something* is accepting TCP connections on ``host:port``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False


def _probe_dev_server(url: str, timeout: float) -> bool:
    """Quick HEAD-ish probe on the dev URL. Any response is good enough."""
    try:
        with urlopen(Request(url, method="GET"), timeout=timeout) as resp:
            # 2xx/3xx/4xx all mean "server is up"; only network error kills us.
            return 200 <= resp.status < 500
    except (URLError, TimeoutError, OSError):
        return False


def _wait_for_backend(timeout: float) -> bool:
    """Block until :8765 is listening, up to ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_in_use(BACKEND_HOST, BACKEND_WS_PORT, timeout=0.2):
            return True
        time.sleep(BACKEND_POLL_INTERVAL_S)
    return False


def _spawn_backend() -> subprocess.Popen[bytes]:
    """Start ``python -m src.main`` as a subprocess and register atexit cleanup."""
    logger.info(f"desktop: spawning backend — {sys.executable} -m src.main (cwd={REPO_ROOT})")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"

    creationflags = 0
    if sys.platform == "win32":
        # Prevent a console window from flashing when pythonw.exe is the parent.
        # CREATE_NO_WINDOW = 0x08000000 on Windows.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.main"],
        cwd=str(REPO_ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    atexit.register(_stop_backend)
    return proc


def _stop_backend() -> None:
    """Terminate the backend subprocess if we spawned one."""
    global _backend_proc
    proc = _backend_proc
    if proc is None:
        return
    _backend_proc = None
    if proc.poll() is not None:
        return
    logger.info("desktop: stopping backend subprocess")
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            logger.warning("desktop: backend did not exit in 5 s — killing")
            proc.kill()
            proc.wait(timeout=2.0)
    except Exception as exc:
        logger.warning(f"desktop: backend stop raised {exc!r}")


def _ensure_backend() -> str:
    """Attach to an existing backend or spawn a fresh one. Returns the mode used."""
    global _backend_proc
    if _port_in_use(BACKEND_HOST, BACKEND_WS_PORT):
        logger.info(f"desktop: backend already listening on :{BACKEND_WS_PORT} — attaching")
        return "attached"
    _backend_proc = _spawn_backend()
    if _wait_for_backend(BACKEND_SPAWN_TIMEOUT_S):
        logger.info("desktop: backend subprocess ready")
    else:
        logger.error(
            f"desktop: backend subprocess did not bind :{BACKEND_WS_PORT} within "
            f"{BACKEND_SPAWN_TIMEOUT_S}s — window will load anyway, UI will retry"
        )
    return "spawned"


def _choose_url() -> str:
    """Return the URL the webview should load — dev server first, static export second."""
    if _probe_dev_server(DEV_URL, DEV_PROBE_TIMEOUT_S):
        logger.info(f"desktop: Next.js dev server reachable — loading {DEV_URL}")
        return DEV_URL
    if FRONTEND_INDEX.exists():
        url = FRONTEND_INDEX.as_uri()
        logger.info(f"desktop: loading static export at {url}")
        return url
    logger.warning(
        f"desktop: neither dev server (on {DEV_URL}) nor static export "
        f"({FRONTEND_INDEX}) is available — window will show a blank page. "
        "Run `cd frontend && npm run dev` or `npm run build`."
    )
    # Still return a file URI so pywebview opens; user will see a browser
    # 'file not found' page, which is a legible failure mode.
    return FRONTEND_INDEX.as_uri()


def main() -> int:
    """Bring up backend, webview window, and block until the user closes it."""
    logger.info(f"=== Aether desktop shell — repo_root={REPO_ROOT} ===")
    backend_mode = _ensure_backend()
    url = _choose_url()

    bridge = DesktopBridge()
    window = webview.create_window(
        title=WINDOW_TITLE,
        url=url,
        js_api=bridge,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN_SIZE,
        background_color=WINDOW_BG,
        text_select=True,
        confirm_close=False,
    )
    bridge.attach_window(window)

    def _on_closed() -> None:
        logger.info(f"desktop: window closed (backend_mode={backend_mode})")
        # atexit will also stop the backend, but stopping here gives a tighter
        # close latency than waiting for the interpreter to tear down.
        _stop_backend()

    window.events.closed += _on_closed

    webview.start(debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
