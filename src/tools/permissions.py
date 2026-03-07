"""Permissions system — centralized permission checks for all tool actions.

Reads from aether_config.yaml permissions section. Provides check_permission()
that returns ALLOW/DENY/CONFIRM for any action+target combination.
"""

from pathlib import Path

from loguru import logger

from src.shared.config import get_yaml_config
from src.tools.approval_gate import ActionRisk

# Default blocked paths (also in file_ops.py — canonical source is config)
_DEFAULT_BLOCKED_PATHS = [".ssh", ".aws", ".gnupg", "id_rsa", "credentials", ".env"]

# Default blocked shell commands
_DEFAULT_BLOCKED_COMMANDS = ["rm -rf", "del /s", "format", "shutdown", "regedit", "net user"]

# Default safe write directories
_DEFAULT_SAFE_WRITE_DIRS = ["~/Documents", "./data"]


def _get_permissions_config() -> dict:
    """Get permissions section from config."""
    config = get_yaml_config()
    return config.get("permissions", {})


def get_blocked_paths() -> list[str]:
    """Get list of blocked path patterns."""
    perms = _get_permissions_config()
    return perms.get("blocked_paths", _DEFAULT_BLOCKED_PATHS)


def get_blocked_commands() -> list[str]:
    """Get list of blocked shell commands."""
    perms = _get_permissions_config()
    return perms.get("blocked_commands", _DEFAULT_BLOCKED_COMMANDS)


def get_safe_write_dirs() -> list[Path]:
    """Get list of directories where file writes are allowed."""
    perms = _get_permissions_config()
    raw_dirs = perms.get("safe_write_dirs", _DEFAULT_SAFE_WRITE_DIRS)
    return [Path(d).expanduser().resolve() for d in raw_dirs]


def get_allowed_apps() -> list[str]:
    """Get list of allowed application names."""
    perms = _get_permissions_config()
    return perms.get("allowed_apps", [])


def is_path_blocked(path_str: str) -> bool:
    """Check if a path contains any blocked patterns (component matching).

    Uses path component matching (not substring) consistent with file_ops.py.
    This prevents bypasses like '/safe/.env_data/' matching '.env'.
    """
    try:
        path = Path(path_str).resolve()
    except Exception:
        return True  # Invalid path = treat as blocked
    path_parts_lower = [p.lower() for p in path.parts]
    path_name_lower = path.name.lower()
    for blocked in get_blocked_paths():
        blocked_lower = blocked.lower()
        if blocked_lower in path_parts_lower or blocked_lower == path_name_lower:
            return True
    return False


def is_command_blocked(command: str) -> bool:
    """Check if a shell command matches any blocked patterns.

    Delegates to shell_exec.is_command_safe() which uses regex patterns
    for stronger matching (prevents bypass via chaining, encoding, etc.).
    """
    from src.tools.shell_exec import is_command_safe

    safe, _ = is_command_safe(command)
    return not safe


def is_path_writable(path_str: str) -> bool:
    """Check if a path is under a safe write directory."""
    try:
        resolved = Path(path_str).resolve()
        safe_dirs = get_safe_write_dirs()
        return any(resolved.is_relative_to(safe_dir) for safe_dir in safe_dirs)
    except Exception:
        return False


def check_permission(action: str, target: str = "") -> tuple[ActionRisk, bool]:
    """Check permission for an action on a target.

    Returns (risk_level, denied):
    - risk_level: ActionRisk.SAFE / CONFIRM / EXPLICIT
    - denied: True if this is a hard DENY (blocked path/command). Caller MUST
      reject the action regardless of approval status.

    Hard DENY vs EXPLICIT: EXPLICIT asks the user for approval. Hard DENY
    rejects unconditionally — no amount of approval overrides it.
    """
    action_lower = action.lower()

    # File read — check blocked paths
    if action_lower == "read_file":
        if is_path_blocked(target):
            logger.warning(f"Permissions: DENIED read of blocked path '{target}'")
            return ActionRisk.EXPLICIT, True
        return ActionRisk.SAFE, False

    # File write — check blocked paths + writable dirs
    if action_lower in ("write_to_file", "create_directory"):
        if is_path_blocked(target):
            logger.warning(f"Permissions: DENIED write to blocked path '{target}'")
            return ActionRisk.EXPLICIT, True
        if not is_path_writable(target):
            logger.warning(f"Permissions: DENIED write outside safe dirs '{target}'")
            return ActionRisk.EXPLICIT, False
        return ActionRisk.CONFIRM, False

    # Shell commands — check blocked commands
    if action_lower == "run_command":
        if is_command_blocked(target):
            logger.warning(f"Permissions: DENIED blocked command '{target}'")
            return ActionRisk.EXPLICIT, True
        return ActionRisk.CONFIRM, False

    # App launch — check allowlist
    if action_lower == "open_application":
        allowed = get_allowed_apps()
        if allowed and target.lower() not in allowed:
            logger.warning(f"Permissions: app '{target}' not in allowlist")
            return ActionRisk.EXPLICIT, True
        return ActionRisk.SAFE, False

    # File delete — always explicit
    if action_lower in ("delete_file", "move_file"):
        return ActionRisk.EXPLICIT, False

    # Screenshot, clipboard, list — safe
    if action_lower in (
        "take_screenshot",
        "get_clipboard",
        "list_running_apps",
        "list_directory",
        "search_files",
        "focus_window",
        "get_active_window_title",
        "minimize_window",
        "maximize_window",
    ):
        return ActionRisk.SAFE, False

    # Close window — confirm (could lose unsaved work)
    if action_lower == "close_window":
        return ActionRisk.CONFIRM, False

    # Default: confirm for unknown actions
    logger.info(f"Permissions: unknown action '{action}', defaulting to CONFIRM")
    return ActionRisk.CONFIRM, False
