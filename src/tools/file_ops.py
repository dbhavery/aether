"""File operations tools — read, write, list, search, create directories.

SECURITY: Path validation prevents traversal. Blocked paths enforced.
Size limits: read max 1MB, write max 100KB.
"""

from pathlib import Path

from loguru import logger

from src.shared.config import get_yaml_config

# Max sizes
MAX_READ_BYTES = 1_048_576  # 1MB
MAX_WRITE_BYTES = 102_400  # 100KB

# Default blocked paths
_DEFAULT_BLOCKED = [".ssh", ".aws", ".gnupg", "id_rsa", "credentials", ".env"]


def _get_blocked_paths() -> list[str]:
    """Get blocked path patterns from config."""
    config = get_yaml_config()
    return config.get("permissions", {}).get("blocked_paths", _DEFAULT_BLOCKED)


def _get_safe_write_dirs() -> list[Path]:
    """Get directories where writes are allowed."""
    config = get_yaml_config()
    raw_dirs = config.get("permissions", {}).get("safe_write_dirs", ["~/Documents", "./data"])
    return [Path(d).expanduser().resolve() for d in raw_dirs]


def _validate_path(path_str: str, require_writable: bool = False) -> tuple[bool, str, Path | None]:
    """Validate a file path for safety.

    Returns (is_valid, error_message, resolved_path).
    """
    try:
        path = Path(path_str).resolve()
    except Exception as e:
        return False, f"Invalid path: {e}", None

    # Check blocked patterns using path component matching (not substring)
    path_parts_lower = [p.lower() for p in path.parts]
    path_name_lower = path.name.lower()
    for blocked in _get_blocked_paths():
        blocked_lower = blocked.lower()
        # Check against individual path components and the filename
        if blocked_lower in path_parts_lower or blocked_lower == path_name_lower:
            return False, f"Access denied: path contains blocked pattern '{blocked}'", None

    # Check for path traversal
    if ".." in path.parts:
        return False, "Access denied: path traversal detected", None

    # For writes, verify the path is under a safe directory
    if require_writable:
        safe_dirs = _get_safe_write_dirs()
        is_safe = any(path.is_relative_to(safe_dir) for safe_dir in safe_dirs)
        if not is_safe:
            return False, f"Write denied: path not under allowed directories: {[str(d) for d in safe_dirs]}", None

    return True, "", path


async def read_file(path: str, max_bytes: int | None = None) -> dict:
    """Read a file's contents. Max 1MB by default."""
    valid, error, resolved = _validate_path(path)
    if not valid:
        return {"success": False, "error": error}

    if not resolved.exists():
        return {"success": False, "error": f"File not found: {path}"}

    if not resolved.is_file():
        return {"success": False, "error": f"Not a file: {path}"}

    limit = min(max_bytes or MAX_READ_BYTES, MAX_READ_BYTES)
    file_size = resolved.stat().st_size

    if file_size > limit:
        return {"success": False, "error": f"File too large ({file_size} bytes, max {limit})"}

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
        logger.info(f"Tools: read file '{resolved}' ({len(content)} chars)")
        return {"success": True, "content": content, "path": str(resolved), "size": file_size}
    except Exception as e:
        logger.error(f"Tools: read_file error: {e}")
        return {"success": False, "error": str(e)}


async def write_to_file(path: str, content: str, append: bool = False) -> dict:
    """Write content to a file. Max 100KB. Only in safe write dirs."""
    valid, error, resolved = _validate_path(path, require_writable=True)
    if not valid:
        return {"success": False, "error": error}

    if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
        return {"success": False, "error": f"Content too large (max {MAX_WRITE_BYTES} bytes)"}

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with resolved.open("a", encoding="utf-8") as f:
                f.write(content)
        else:
            resolved.write_text(content, encoding="utf-8")
        logger.info(f"Tools: wrote {len(content)} chars to '{resolved}' (append={append})")
        return {"success": True, "path": str(resolved), "chars_written": len(content)}
    except Exception as e:
        logger.error(f"Tools: write_to_file error: {e}")
        return {"success": False, "error": str(e)}


async def list_directory(path: str, max_items: int = 100) -> dict:
    """List contents of a directory."""
    valid, error, resolved = _validate_path(path)
    if not valid:
        return {"success": False, "error": error}

    if not resolved.exists():
        return {"success": False, "error": f"Directory not found: {path}"}

    if not resolved.is_dir():
        return {"success": False, "error": f"Not a directory: {path}"}

    try:
        items = []
        for item in sorted(resolved.iterdir())[:max_items]:
            try:
                size = item.stat().st_size if item.is_file() else None
            except OSError:
                size = None
            items.append(
                {
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": size,
                }
            )
        logger.info(f"Tools: listed {len(items)} items in '{resolved}'")
        return {"success": True, "path": str(resolved), "items": items}
    except Exception as e:
        logger.error(f"Tools: list_directory error: {e}")
        return {"success": False, "error": str(e)}


async def search_files(directory: str, pattern: str, max_results: int = 50) -> dict:
    """Search for files matching a glob pattern in a directory."""
    # Reject patterns that could traverse outside the search directory
    if ".." in pattern:
        return {"success": False, "error": "Pattern must not contain '..'"}

    valid, error, resolved = _validate_path(directory)
    if not valid:
        return {"success": False, "error": error}

    if not resolved.is_dir():
        return {"success": False, "error": f"Not a directory: {directory}"}

    try:
        matches = []
        for match in resolved.rglob(pattern):
            if len(matches) >= max_results:
                break
            # Verify result is still under search root (prevent traversal via symlinks)
            try:
                if not match.resolve().is_relative_to(resolved):
                    continue
            except (OSError, ValueError):
                continue
            # Skip blocked paths (component matching, not substring)
            match_parts_lower = [p.lower() for p in match.parts]
            match_name_lower = match.name.lower()
            blocked_list = _get_blocked_paths()
            if any(b.lower() in match_parts_lower or b.lower() == match_name_lower for b in blocked_list):
                continue
            try:
                size = match.stat().st_size if match.is_file() else None
            except OSError:
                size = None
            matches.append(
                {
                    "path": str(match),
                    "name": match.name,
                    "type": "dir" if match.is_dir() else "file",
                    "size": size,
                }
            )
        logger.info(f"Tools: found {len(matches)} files matching '{pattern}' in '{resolved}'")
        return {"success": True, "matches": matches}
    except Exception as e:
        logger.error(f"Tools: search_files error: {e}")
        return {"success": False, "error": str(e)}


async def create_directory(path: str) -> dict:
    """Create a directory (with parents). Only in safe write dirs."""
    valid, error, resolved = _validate_path(path, require_writable=True)
    if not valid:
        return {"success": False, "error": error}

    try:
        resolved.mkdir(parents=True, exist_ok=True)
        logger.info(f"Tools: created directory '{resolved}'")
        return {"success": True, "path": str(resolved)}
    except Exception as e:
        logger.error(f"Tools: create_directory error: {e}")
        return {"success": False, "error": str(e)}
