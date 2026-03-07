"""Tool audit log — logs every tool execution to JSONL for accountability.

Async append to AetherData tool_log.jsonl (non-blocking).
Daily rotation, 30-day retention.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from src.shared.config import get_settings

_log_dir: Path | None = None
_RETENTION_DAYS = 30


def _get_log_dir() -> Path:
    """Lazily resolve log directory — avoids calling get_settings() at import time."""
    global _log_dir
    if _log_dir is None:
        _log_dir = Path(get_settings().aether_data_path)
    return _log_dir


def _get_log_path(date: datetime | None = None) -> Path:
    """Get the log file path for a given date (defaults to today)."""
    if date is None:
        date = datetime.now()
    filename = f"tool_log_{date.strftime('%Y-%m-%d')}.jsonl"
    return _get_log_dir() / filename


async def log_tool_execution(
    tool_name: str,
    args: dict,
    result: str,
    execution_time_ms: float,
    user_approved: bool = True,
) -> None:
    """Log a tool execution to the daily JSONL file.

    Non-blocking — errors are logged but never raised.
    """
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "args": _sanitize_args(args),
            "result_preview": result[:500] if len(result) > 500 else result,
            "execution_time_ms": round(execution_time_ms, 2),
            "user_approved": user_approved,
        }
        log_path = _get_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        import aiofiles

        async with aiofiles.open(str(log_path), "a", encoding="utf-8") as f:
            await f.write(json.dumps(entry) + "\n")
    except ImportError:
        # aiofiles not available — fall back to sync write
        try:
            log_path = _get_log_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e2:
            logger.error(f"AuditLog: sync fallback write failed: {e2}")
    except Exception as e:
        logger.error(f"AuditLog: failed to log tool execution: {e}")


def _sanitize_args(args: dict) -> dict:
    """Remove sensitive values from args before logging."""
    sanitized = {}
    sensitive_keys = {"password", "token", "secret", "key", "api_key", "credential"}
    for k, v in args.items():
        if any(s in k.lower() for s in sensitive_keys):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 1000:
            sanitized[k] = v[:200] + f"... [{len(v)} chars total]"
        else:
            sanitized[k] = v
    return sanitized


def cleanup_old_logs() -> int:
    """Remove log files older than retention period. Returns count of removed files."""
    cutoff = datetime.now() - timedelta(days=_RETENTION_DAYS)
    removed = 0
    try:
        for log_file in _get_log_dir().glob("tool_log_*.jsonl"):
            try:
                # Parse date from filename
                date_str = log_file.stem.replace("tool_log_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    log_file.unlink()
                    removed += 1
                    logger.info(f"AuditLog: removed old log {log_file.name}")
            except (ValueError, OSError) as e:
                logger.warning(f"AuditLog: could not process {log_file.name}: {e}")
    except Exception as e:
        logger.error(f"AuditLog: cleanup failed: {e}")
    return removed


class AuditTimer:
    """Context manager for timing tool executions."""

    def __init__(self) -> None:
        self.start_time: float = 0
        self.elapsed_ms: float = 0

    def __enter__(self) -> "AuditTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000
