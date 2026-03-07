"""Secure API key storage — reads and writes the .env file.

All key operations go through this module so that:
1. os.environ is always kept in sync with the file on disk.
2. Comments and blank lines in the .env file are preserved on write.
3. Keys can be masked for display in the settings UI.

The env file path defaults to {aether_data_path}/.env (from config) but
can be overridden by setting the AETHER_ENV_PATH environment variable.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from loguru import logger


def _default_env_path() -> Path:
    """Resolve default .env path from config. Lazy to avoid import-time issues."""
    try:
        from src.shared.config import get_settings

        return Path(get_settings().aether_data_path) / ".env"
    except Exception:
        return Path(r"./data\.env")


# Regex for a valid KEY=VALUE line (possibly quoted value)
_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)")


def _env_path() -> Path:
    """Resolve the .env file path (configurable via AETHER_ENV_PATH)."""
    override = os.environ.get("AETHER_ENV_PATH", "").strip()
    if override:
        return Path(override)
    return _default_env_path()


# ---------------------------------------------------------------------------
# Internal I/O
# ---------------------------------------------------------------------------


def _read_env_file() -> list[str]:
    """Read the .env file and return its lines (including comments/blanks).

    Returns an empty list if the file does not exist yet.
    """
    path = _env_path()
    if not path.exists():
        logger.info(f".env file not found at {path} — will be created on first write")
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.error(f"Failed to read .env at {path}: {exc}")
        raise


def _write_env_file(lines: list[str]) -> None:
    """Write lines back to the .env file, preserving comments and order.

    Creates parent directories if they do not exist.
    """
    path = _env_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.debug(f".env written ({len(lines)} lines) to {path}")
    except OSError as exc:
        logger.error(f"Failed to write .env at {path}: {exc}")
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_key(env_var: str) -> str | None:
    """Return the value for *env_var* from the .env file (and os.environ).

    Checks os.environ first (it may have been set externally).  Falls back to
    reading the file directly so freshly-written keys are always visible.

    Returns None if the key is not set anywhere.
    """
    # Fast path: already in environment
    value = os.environ.get(env_var, "").strip()
    if value:
        return value

    # Slower path: scan the file
    for line in _read_env_file():
        match = _KV_RE.match(line.strip())
        if match and match.group(1) == env_var:
            raw = match.group(2).strip()
            # Strip surrounding quotes if present
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
                raw = raw[1:-1]
            if raw:
                # Backfill into os.environ so subsequent reads are fast
                os.environ[env_var] = raw
                return raw

    return None


def set_key(env_var: str, value: str) -> None:
    """Set *env_var* = *value* in both the .env file and os.environ.

    If the key already exists in the file its line is updated in-place.
    Otherwise a new line is appended at the end.
    """
    if not env_var or not value:
        logger.error(f"set_key called with empty env_var={env_var!r} or value")
        raise ValueError("env_var and value must be non-empty strings")

    lines = _read_env_file()
    found = False

    # Quote values that contain spaces, quotes, or # (comment char) to survive round-trip
    needs_quoting = any(c in value for c in (" ", "'", '"', "#", "\t"))
    safe_value = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"' if needs_quoting else value

    for idx, line in enumerate(lines):
        match = _KV_RE.match(line.strip())
        if match and match.group(1) == env_var:
            lines[idx] = f"{env_var}={safe_value}"
            found = True
            break

    if not found:
        lines.append(f"{env_var}={safe_value}")

    _write_env_file(lines)
    os.environ[env_var] = value
    logger.info(f"Key set: {env_var} (length {len(value)})")


def delete_key(env_var: str) -> bool:
    """Remove *env_var* from the .env file and os.environ.

    Returns True if the key was found and removed, False if it was not present.
    """
    lines = _read_env_file()
    new_lines: list[str] = []
    removed = False

    for line in lines:
        match = _KV_RE.match(line.strip())
        if match and match.group(1) == env_var:
            removed = True
            continue  # skip this line
        new_lines.append(line)

    if removed:
        _write_env_file(new_lines)
        os.environ.pop(env_var, None)
        logger.info(f"Key deleted: {env_var}")
    else:
        logger.debug(f"delete_key: {env_var} was not present in .env")

    return removed


def mask_key(value: str | None, visible_chars: int = 4) -> str:
    """Return a masked version of *value* suitable for UI display.

    Shows the last *visible_chars* characters, replaces the rest with bullets.
    Returns "(not set)" for None or empty values.

    >>> mask_key("sk-abc123xyz")
    '•••••••xyz'
    >>> mask_key(None)
    '(not set)'
    """
    if not value:
        return "(not set)"

    if len(value) <= visible_chars:
        # Too short to meaningfully mask — show bullets only
        return "•" * len(value)

    hidden_count = len(value) - visible_chars
    return "•" * hidden_count + value[-visible_chars:]
