"""Input validation helpers — path sanitization, port validation, URL validation.

Used at system boundaries (user input, tool arguments, config values).
"""

import re
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

# Paths that must never be accessed by tools or file operations
BLOCKED_PATH_SEGMENTS = frozenset(
    {
        ".ssh",
        ".aws",
        ".gnupg",
        "id_rsa",
        "id_ed25519",
        "credentials",
        ".env",
        ".git",
        "node_modules",
    }
)


def sanitize_path(path_str: str, allowed_roots: list[str] | None = None) -> Path | None:
    """Validate and resolve a file path. Returns None if unsafe.

    Checks:
    - No path traversal (../)
    - No blocked path segments (.ssh, .aws, credentials, etc.)
    - If allowed_roots given, path must be under one of them
    """
    try:
        resolved = Path(path_str).resolve()
    except (OSError, ValueError) as e:
        logger.warning(f"Validation: invalid path '{path_str}': {e}")
        return None

    # Check for blocked segments
    parts_lower = {p.lower() for p in resolved.parts}
    blocked = parts_lower & BLOCKED_PATH_SEGMENTS
    if blocked:
        logger.warning(f"Validation: blocked path segment(s) {blocked} in '{path_str}'")
        return None

    # Check allowed roots
    if allowed_roots:
        resolved_str = str(resolved)
        if not any(resolved_str.startswith(str(Path(root).resolve())) for root in allowed_roots):
            logger.warning(f"Validation: path '{path_str}' not under allowed roots")
            return None

    return resolved


def validate_port(port: int | str) -> int | None:
    """Validate a network port number. Returns int or None if invalid."""
    try:
        port_int = int(port)
    except (ValueError, TypeError):
        return None
    if 1 <= port_int <= 65535:
        return port_int
    return None


def validate_url(url: str) -> str | None:
    """Validate a URL. Returns cleaned URL or None if invalid."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https", "ws", "wss"):
            return None
        if not parsed.netloc:
            return None
        return url
    except Exception:
        return None


# Regex for validating model names (alphanumeric + dots, colons, hyphens, underscores)
_MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}$")


def validate_model_name(name: str) -> bool:
    """Check if a model name looks valid (safe chars, reasonable length)."""
    return bool(_MODEL_NAME_RE.match(name))
