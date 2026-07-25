"""
Avatar server launcher — tries PersonaLive first, falls back to LivePortrait.
Both servers expose the same REST API contract on port 8770.

This module is called from startup.py to launch the avatar backend.
The desktop client talks to whichever server is running via AvatarClient.
"""

import asyncio
import atexit
import contextlib
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from loguru import logger

from src.shared.config import get_yaml_config


def _get_avatar_paths() -> dict:
    """Resolve avatar backend paths from config, with defaults."""
    config = get_yaml_config()
    avatar_cfg = config.get("avatar", {})

    pl_dir = Path(avatar_cfg.get("personalive_dir", r"~\Projects\personalive"))
    lp_dir = Path(avatar_cfg.get("liveportrait_dir", r"~\Projects\LivePortrait"))

    return {
        "personalive_dir": pl_dir,
        "personalive_server": pl_dir / "aether_server.py",
        "personalive_python": pl_dir / ".venv" / "Scripts" / "python.exe",
        "liveportrait_dir": lp_dir,
        "liveportrait_server": lp_dir / "aether_api.py",
        "liveportrait_python": lp_dir / ".venv" / "Scripts" / "python.exe",
    }


HEALTH_URL = "http://localhost:8770/health"
AVATAR_PORT = 8770
MAX_WAIT = 45  # seconds — PersonaLive needs time to load models

# Track the avatar subprocess and log file handle for cleanup
_avatar_proc: subprocess.Popen | None = None
_avatar_log_fh = None


def _cleanup_avatar() -> None:
    """Terminate the avatar subprocess if it's still running."""
    global _avatar_proc, _avatar_log_fh
    if _avatar_log_fh is not None:
        with contextlib.suppress(Exception):
            if not _avatar_log_fh.closed:
                _avatar_log_fh.close()
        _avatar_log_fh = None
    if _avatar_proc is None or _avatar_proc.poll() is not None:
        _avatar_proc = None
        return
    logger.info("Avatar: terminating subprocess...")
    _avatar_proc.terminate()
    try:
        _avatar_proc.wait(timeout=5)
        logger.info("Avatar: subprocess stopped cleanly")
    except subprocess.TimeoutExpired:
        _avatar_proc.kill()
        logger.warning("Avatar: subprocess force-killed (timeout)")
    _avatar_proc = None


def _kill_stale_avatar_process() -> None:
    """Kill any process already holding port 8770 before starting a new one."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        sock.connect(("localhost", AVATAR_PORT))
    except (TimeoutError, ConnectionRefusedError, OSError):
        return  # Port is free
    finally:
        sock.close()

    # Port is in use — find and kill the process
    try:
        result = subprocess.run(  # nosec B603 B607  # trusted netstat command
            ["netstat", "-ano"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{AVATAR_PORT} " in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if not pid.isdigit():
                    logger.warning(f"Avatar: skipping non-numeric PID from netstat: {pid!r}")
                    continue
                subprocess.run(  # nosec B603 B607  # trusted taskkill
                    ["taskkill", "/F", "/PID", pid],  # noqa: S607
                    capture_output=True,
                    timeout=5,
                )
                logger.info(f"Avatar: killed stale process on port {AVATAR_PORT} (PID {pid})")
                break
    except Exception as e:
        logger.debug(f"Avatar: stale process check failed: {e}")


# Register cleanup on normal exit
atexit.register(_cleanup_avatar)


async def start_avatar_server() -> str:
    """Start avatar server. Returns engine name or 'none' if both fail."""
    global _avatar_proc, _avatar_log_fh

    paths = _get_avatar_paths()

    # Kill any stale process from a previous unclean exit
    _kill_stale_avatar_process()

    # Try PersonaLive first
    pl_server = paths["personalive_server"]
    pl_python = paths["personalive_python"]
    pl_dir = paths["personalive_dir"]
    if pl_server.exists() and pl_python.exists():
        logger.info("Avatar: attempting PersonaLive (v2)...")
        try:
            avatar_log = Path(tempfile.gettempdir()) / "aether_avatar.log"
            if _avatar_log_fh is not None and not _avatar_log_fh.closed:
                _avatar_log_fh.close()
            _avatar_log_fh = open(avatar_log, "w")  # noqa: SIM115
            _avatar_proc = subprocess.Popen(
                [str(pl_python), str(pl_server)],
                stdout=_avatar_log_fh,
                stderr=subprocess.STDOUT,
                cwd=str(pl_dir),
            )
            logger.info(f"Avatar: subprocess log at {avatar_log}")
            if await _wait_for_health(MAX_WAIT):
                engine = await _get_engine_name()
                logger.info(f"Avatar: PersonaLive ready (engine={engine})")
                return engine
            else:
                logger.warning("Avatar: PersonaLive failed to start — terminating")
                _cleanup_avatar()
        except Exception as e:
            logger.warning(f"Avatar: PersonaLive launch error: {e}")
            _cleanup_avatar()  # Close file handle on launch failure
    else:
        missing = []
        if not pl_server.exists():
            missing.append(f"server: {pl_server}")
        if not pl_python.exists():
            missing.append(f"python: {pl_python}")
        logger.info(f"Avatar: PersonaLive not found ({', '.join(missing)})")

    # Fall back to LivePortrait
    lp_server = paths["liveportrait_server"]
    lp_python = paths["liveportrait_python"]
    lp_dir = paths["liveportrait_dir"]
    if lp_server.exists() and lp_python.exists():
        logger.info("Avatar: falling back to LivePortrait (v1)...")
        try:
            avatar_log = Path(tempfile.gettempdir()) / "aether_avatar.log"
            if _avatar_log_fh is not None and not _avatar_log_fh.closed:
                _avatar_log_fh.close()
            _avatar_log_fh = open(avatar_log, "w")  # noqa: SIM115
            _avatar_proc = subprocess.Popen(
                [str(lp_python), str(lp_server)],
                stdout=_avatar_log_fh,
                stderr=subprocess.STDOUT,
                cwd=str(lp_dir),
            )
            logger.info(f"Avatar: subprocess log at {avatar_log}")
            if await _wait_for_health(30):
                engine = await _get_engine_name()
                logger.info(f"Avatar: LivePortrait ready (engine={engine})")
                return engine
            else:
                logger.warning("Avatar: LivePortrait failed to start — terminating")
                _cleanup_avatar()
        except Exception as e:
            logger.warning(f"Avatar: LivePortrait launch error: {e}")
            _cleanup_avatar()  # Close file handle on launch failure
    else:
        logger.info("Avatar: LivePortrait not found — no avatar backend available")

    logger.warning("Avatar: no avatar backend available")
    return "none"


async def _wait_for_health(timeout: int) -> bool:
    """Poll /health endpoint until it responds or times out."""
    deadline = time.time() + timeout
    async with httpx.AsyncClient() as client:
        while time.time() < deadline:
            # Bail early if the subprocess has already exited
            if _avatar_proc is not None and _avatar_proc.poll() is not None:
                logger.warning(f"Avatar: subprocess exited with code {_avatar_proc.returncode} during health wait")
                return False
            try:
                resp = await client.get(HEALTH_URL, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status", "")
                    if status in ("ok", "loading"):
                        return True
            except Exception:
                logger.debug("Avatar: health check pending...")
            await asyncio.sleep(2)
    return False


async def _get_engine_name() -> str:
    """Get the engine name from the health endpoint."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(HEALTH_URL, timeout=3)
            if resp.status_code == 200:
                return resp.json().get("engine", "unknown")
    except Exception:
        logger.debug("Avatar: engine name lookup failed")
    return "unknown"
