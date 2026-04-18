"""WebSocket connection authentication.

Clients must present a valid token in the connection handshake.
Token is generated on first run and stored in <user data dir>/ws_token.txt
(resolved via `src.shared.paths.get_data_dir`). Never hardcoded. Rotates on
explicit request only.
"""

import hashlib
import secrets
import threading
from pathlib import Path

from loguru import logger

from src.shared.paths import get_data_dir

_token_path: Path | None = None
_token_lock = threading.Lock()


def _get_token_path() -> Path:
    """Lazily resolve token path — avoids calling get_data_dir() at import time."""
    global _token_path
    if _token_path is None:
        _token_path = get_data_dir() / "ws_token.txt"
    return _token_path


def _set_token_permissions(path: Path) -> None:
    """Make the token file readable only by the current user (Windows)."""
    try:
        import os
        import subprocess

        username = os.environ.get("USERNAME", "")
        if username:
            subprocess.run(  # noqa: S603  # nosec B603 B607
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:(RW)"],  # noqa: S607
                capture_output=True,
                check=True,
            )
    except Exception as e:
        logger.debug(f"Auth: could not set token file permissions: {e}")


def get_or_create_token() -> str:
    """Return the current shared secret. Creates one on first run."""
    with _token_lock:
        _get_token_path().parent.mkdir(parents=True, exist_ok=True)
        if _get_token_path().exists():
            token = _get_token_path().read_text(encoding="utf-8").strip()
            if token:
                return token
        token = secrets.token_hex(32)
        _get_token_path().write_text(token, encoding="utf-8")
        _set_token_permissions(_get_token_path())
        logger.info(f"Auth: new WS token generated at {_get_token_path()}")
        return token


def rotate_token() -> str:
    """Generate a new token, invalidating all existing client connections."""
    with _token_lock:
        new_token = secrets.token_hex(32)
        _get_token_path().parent.mkdir(parents=True, exist_ok=True)
        _get_token_path().write_text(new_token, encoding="utf-8")
        _set_token_permissions(_get_token_path())
        logger.warning("Auth: token rotated — all clients must reconnect")
        return new_token


def verify_token(presented: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    if not presented:
        return False
    expected = get_or_create_token()
    return secrets.compare_digest(
        hashlib.sha256(presented.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


def get_token_for_client() -> str:
    """Return the token that clients should present."""
    return get_or_create_token()
