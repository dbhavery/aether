"""Single-instance lock — prevents multiple Aether server processes.

Uses a file lock at $AETHER_DATA_PATH/.aether_lock.
Acquire on startup, release on shutdown.
"""

import atexit
import contextlib
import os
from pathlib import Path

from loguru import logger

from src.shared.config import get_settings

_lock_fd = None
_lock_path: str | None = None


def acquire_instance_lock() -> bool:
    """Try to acquire the instance lock. Returns True on success, False if another instance holds it."""
    global _lock_fd, _lock_path

    lock_dir = Path(get_settings().aether_data_path)
    lock_dir.mkdir(parents=True, exist_ok=True)
    _lock_path = str(lock_dir / ".aether_lock")

    try:
        import msvcrt

        _lock_fd = open(_lock_path, "w")  # noqa: SIM115
        msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        atexit.register(release_instance_lock)
        logger.info(f"InstanceLock: acquired — PID {os.getpid()}")
        return True
    except (OSError, ImportError) as e:
        logger.error(f"InstanceLock: failed to acquire lock — another instance running? {e}")
        if _lock_fd:
            _lock_fd.close()
            _lock_fd = None
        return False


def release_instance_lock() -> None:
    """Release the instance lock."""
    global _lock_fd, _lock_path

    if _lock_fd is None:
        return

    try:
        import msvcrt

        _lock_fd.seek(0)  # Must match position 0 where LK_NBLCK was called
        msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
        logger.info("InstanceLock: released")
    except Exception as e:
        logger.debug(f"InstanceLock: error releasing lock: {e}")
    finally:
        _lock_fd.close()
        _lock_fd = None

    # Clean up file
    if _lock_path:
        with contextlib.suppress(OSError):
            os.remove(_lock_path)
        _lock_path = None
