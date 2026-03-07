"""Shell command execution tool — run commands with safety checks.

SECURITY: Blocked commands enforced. All commands require approval gate.
Timeout: 30s default. Returns stdout + stderr + exit code.
"""

import asyncio
import re

from loguru import logger

from src.shared.config import get_yaml_config

# Default blocked commands
_DEFAULT_BLOCKED_COMMANDS = [
    "rm -rf",
    "del /s",
    "format",
    "shutdown",
    "regedit",
    "net user",
]

# Blocked patterns (regex)
_BLOCKED_PATTERNS = [
    re.compile(r"\|.*curl", re.IGNORECASE),
    re.compile(r"powershell.*-enc", re.IGNORECASE),
    re.compile(r"reg\s+(add|delete)", re.IGNORECASE),
    re.compile(r"wmic.*delete", re.IGNORECASE),
    re.compile(r"schtasks.*/create", re.IGNORECASE),
    re.compile(r"remove-item.*-recurse", re.IGNORECASE),
    re.compile(r"rm\s+.*-r", re.IGNORECASE),
    re.compile(r"del\s+/[a-z]*s", re.IGNORECASE),
    # Command chaining — prevents blocklist bypass via "safe && dangerous"
    re.compile(r"&&", re.IGNORECASE),
    re.compile(r"\|\|", re.IGNORECASE),
    re.compile(r";", re.IGNORECASE),
    re.compile(r"`", re.IGNORECASE),
    # Dangerous executables that can download/execute arbitrary code
    re.compile(r"\bcertutil\b", re.IGNORECASE),
    re.compile(r"\bbitsadmin\b", re.IGNORECASE),
    re.compile(r"\bmshta\b", re.IGNORECASE),
    re.compile(r"\brundll32\b", re.IGNORECASE),
    re.compile(r"\bcscript\b", re.IGNORECASE),
    re.compile(r"\bwscript\b", re.IGNORECASE),
]


def _get_blocked_commands() -> list[str]:
    """Get blocked command strings from config."""
    config = get_yaml_config()
    return config.get("permissions", {}).get("blocked_commands", _DEFAULT_BLOCKED_COMMANDS)


def is_command_safe(command: str) -> tuple[bool, str]:
    """Check if a command is safe to execute.

    Returns (is_safe, reason_if_blocked).
    """
    # Normalize whitespace to prevent bypass via extra spaces/tabs
    cmd_lower = " ".join(command.lower().split())

    # Check exact blocked commands
    for blocked in _get_blocked_commands():
        if blocked.lower() in cmd_lower:
            return False, f"Blocked command pattern: '{blocked}'"

    # Check regex patterns
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(command):
            return False, f"Blocked command pattern: {pattern.pattern}"

    return True, ""


async def run_command(command: str, timeout: int = 30) -> dict:
    """Execute a shell command and return results.

    All commands go through the approval gate in the handler.
    This function does NOT check approval — the dispatcher handles that.
    """
    # Safety check
    safe, reason = is_command_safe(command)
    if not safe:
        logger.warning(f"Tools: blocked command '{command[:60]}': {reason}")
        return {
            "success": False,
            "error": f"Command blocked: {reason}",
            "exit_code": -1,
        }

    # Cap timeout at 60s
    timeout = min(timeout, 60)

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.communicate()
            logger.warning(f"Tools: command timed out after {timeout}s: '{command[:60]}'")
            return {
                "success": False,
                "error": f"Command timed out after {timeout}s",
                "exit_code": -1,
            }

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        exit_code = process.returncode

        # Truncate very long output
        max_output = 10_000
        if len(stdout_text) > max_output:
            stdout_text = stdout_text[:max_output] + f"\n... (truncated, {len(stdout_text)} total chars)"
        if len(stderr_text) > max_output:
            stderr_text = stderr_text[:max_output] + f"\n... (truncated, {len(stderr_text)} total chars)"

        logger.info(f"Tools: command '{command[:60]}' exited with {exit_code}")
        return {
            "success": exit_code == 0,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "exit_code": exit_code,
        }
    except Exception as e:
        logger.error(f"Tools: run_command error: {e}")
        return {"success": False, "error": str(e), "exit_code": -1}
