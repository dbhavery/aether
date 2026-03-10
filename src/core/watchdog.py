"""Process watchdog — monitors server health and auto-restarts on crash.

Runs as a wrapper around the main server process.
Checks the health endpoint periodically and restarts if unresponsive.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from loguru import logger

# Project root — used to set CWD and VIRTUAL_ENV for child processes
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_VENV_DIR = _PROJECT_ROOT / ".venv"

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


CHECK_INTERVAL_S = 15
MAX_CONSECUTIVE_FAILURES = 5
STARTUP_GRACE_S = 30
BASE_RESTART_DELAY = 5.0
MAX_RESTART_DELAY = 300.0  # 5 minutes
MAX_RESTART_ATTEMPTS = 10
# If server runs longer than this, reset the restart counter
STABLE_RUN_THRESHOLD_S = 60


def _get_health_url() -> str:
    """Resolve health endpoint URL from config.

    Always connect to 127.0.0.1 (not the bind address).
    When the server binds to 0.0.0.0, it listens on all interfaces
    but 0.0.0.0 is not a valid connect target on Windows.
    """
    try:
        from src.shared.config import get_settings

        settings = get_settings()
        return f"http://127.0.0.1:{settings.health_port}/health"
    except Exception:
        return "http://127.0.0.1:8767/health"


async def check_health() -> bool:
    """Ping the health endpoint. Returns True if healthy."""
    if not _HTTPX_AVAILABLE:
        logger.warning("Watchdog: httpx not installed — health checking disabled, assuming unhealthy")
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(_get_health_url())
            return resp.status_code == 200
    except Exception:
        return False


async def watchdog_loop(server_cmd: list[str] | None = None) -> None:
    """Run the watchdog loop.

    If server_cmd is provided, the watchdog manages the server process lifecycle.
    Otherwise, it just monitors health and logs warnings.
    """
    if server_cmd is None:
        # Use the venv python explicitly to avoid VIRTUAL_ENV contamination
        # from VS Code or other shells pointing to the wrong project.
        python_exe = (
            str(_VENV_DIR / "Scripts" / "python.exe") if sys.platform == "win32" else str(_VENV_DIR / "bin" / "python")
        )
        server_cmd = [python_exe, "-m", "src.main"]

    logger.info(f"Watchdog: starting. Health URL: {_get_health_url()}")
    logger.info(f"Watchdog: server command: {' '.join(server_cmd)}")

    restart_attempt = 0
    stderr_file = None
    while True:
        # Start the server process
        restart_attempt += 1
        if restart_attempt > MAX_RESTART_ATTEMPTS:
            logger.critical(f"Watchdog: {MAX_RESTART_ATTEMPTS} consecutive restarts — giving up")
            _notify_crash(-99)
            return

        logger.info(f"Watchdog: launching server process (attempt {restart_attempt})")
        try:
            # Build a clean environment with correct VIRTUAL_ENV
            child_env = os.environ.copy()
            child_env["VIRTUAL_ENV"] = str(_VENV_DIR)

            # Close previous stderr file handle if still open from last iteration
            if stderr_file is not None and not stderr_file.closed:
                stderr_file.close()

            # Redirect stderr to a log file (not DEVNULL) so crashes are visible.
            try:
                from src.shared.config import get_settings

                stderr_log = Path(get_settings().aether_data_path) / "logs" / "server_stderr.log"
            except Exception:
                stderr_log = Path("./data/logs/server_stderr.log")
            stderr_log.parent.mkdir(parents=True, exist_ok=True)
            stderr_file = open(stderr_log, "a")  # noqa: SIM115

            popen_kwargs: dict = {
                "cwd": str(_PROJECT_ROOT),
                "env": child_env,
                "stdout": subprocess.DEVNULL,
                "stderr": stderr_file,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(  # noqa: S603  # trusted server_cmd from within watchdog
                server_cmd,
                **popen_kwargs,
            )
        except Exception as e:
            logger.error(f"Watchdog: failed to start server: {e}")
            if stderr_file is not None and not stderr_file.closed:
                stderr_file.close()
            delay = min(BASE_RESTART_DELAY * (2 ** (restart_attempt - 1)), MAX_RESTART_DELAY)
            logger.info(f"Watchdog: retrying in {delay:.0f}s...")
            await asyncio.sleep(delay)
            continue

        logger.info(f"Watchdog: server PID={proc.pid}. Waiting {STARTUP_GRACE_S}s for startup...")
        start_time = asyncio.get_event_loop().time()
        await asyncio.sleep(STARTUP_GRACE_S)

        # Monitor health
        consecutive_failures = 0
        while True:
            # Check if process is still alive
            if proc.poll() is not None:
                exit_code = proc.returncode
                logger.warning(f"Watchdog: server process exited with code {exit_code}")
                _notify_crash(exit_code)
                break

            healthy = await check_health()
            if healthy:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logger.warning(f"Watchdog: health check failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})")

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error("Watchdog: server unresponsive. Killing and restarting.")
                _notify_crash(-1)
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                except Exception as e:
                    logger.error(f"Watchdog: failed to kill server: {e}")
                break

            await asyncio.sleep(CHECK_INTERVAL_S)

        # Close stderr file handle before restart
        if stderr_file is not None and not stderr_file.closed:
            stderr_file.close()

        # If server ran longer than the stable threshold, reset the counter
        run_duration = asyncio.get_event_loop().time() - start_time
        if run_duration > STABLE_RUN_THRESHOLD_S:
            restart_attempt = 0

        # Exponential backoff before restart
        delay = min(BASE_RESTART_DELAY * (2 ** (restart_attempt - 1)), MAX_RESTART_DELAY)
        logger.info(f"Watchdog: restarting in {delay:.0f}s (attempt {restart_attempt})...")
        await asyncio.sleep(delay)


def _notify_crash(exit_code: int) -> None:
    """Send crash notifications through all available channels."""
    message = f"Aether server exited (code {exit_code}). Auto-restarting..."

    # Windows toast notification
    try:
        from winotify import Notification

        toast = Notification(
            app_id="Aether",
            title="Server Crashed",
            msg=message,
        )
        toast.show()
    except ImportError:
        logger.debug("Watchdog: winotify not installed, crash notification skipped")
    except Exception as e:
        logger.debug(f"Watchdog: toast notification failed: {e}")

    # Telegram notification (if configured)
    try:
        import os

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if token and chat_id:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": f"Aether: {message}"},
                )
                logger.info("Watchdog: Telegram crash notification sent")
    except Exception as e:
        logger.debug(f"Watchdog: Telegram notification failed: {e}")


def is_already_running() -> bool:
    """Check if another instance is already running on any of our ports."""
    import socket

    try:
        from src.shared.config import get_settings

        settings = get_settings()
        ports = (settings.websocket_port, settings.health_port)
    except Exception:
        ports = (8765, 8767)

    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.settimeout(1)
                sock.connect(("localhost", port))
                return True
            except (TimeoutError, ConnectionRefusedError, OSError):
                continue
    return False


if __name__ == "__main__":
    if is_already_running():
        logger.info("Watchdog: server already running. Exiting.")
        sys.exit(0)
    asyncio.run(watchdog_loop())
