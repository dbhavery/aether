"""Token-usage logging, cost estimation, and soft per-provider daily budgets.

Everything is append-only JSONL at ``<data_dir>/usage.jsonl`` for the usage
stream and ``<data_dir>/budgets.json`` for user-set budgets. Keeping these as
flat files means:

* The user's data directory is portable (``zip -r aether-data.zip .`` works).
* We don't need a SQL migration story for a v1.0 feature this small.
* Rolling up a day's usage is a linear scan of a tiny file.

All I/O is wrapped through ``asyncio.to_thread`` so nothing blocks the event
loop — per the project-wide no-blocking-calls rule.

Cost estimation uses litellm's ``cost_per_token`` when available, which covers
the cloud providers we care about. Local models (Ollama, anything starting with
``ollama/``) are always $0.00; we still log their token counts for parity with
the Sandbox -> Usage UI.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

from loguru import logger

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------


def _data_dir() -> Path:
    """Return the user's Aether data directory (creating it if missing)."""
    from src.shared.paths import get_data_dir

    path = get_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _usage_path() -> Path:
    return _data_dir() / "usage.jsonl"


def _budgets_path() -> Path:
    return _data_dir() / "budgets.json"


# ---------------------------------------------------------------------------
# Token usage logging
# ---------------------------------------------------------------------------


_LOCAL_PROVIDER_PREFIXES: Final[tuple[str, ...]] = ("ollama",)


def _is_local(provider: str, model: str) -> bool:
    p = provider.lower()
    if p in _LOCAL_PROVIDER_PREFIXES:
        return True
    return model.lower().startswith("ollama/")


def _estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate request cost via litellm's cost table. Returns 0.0 if unknown or local."""
    if _is_local(provider, model):
        return 0.0
    try:
        import litellm

        # ``cost_per_token`` returns (input_cost, output_cost) per-token in USD.
        input_cost, output_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return float(input_cost + output_cost)
    except Exception as exc:
        logger.debug(f"Cost: no pricing for '{model}' ({exc!r}) — recording $0.00")
        return 0.0


async def track_usage(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Append one usage record to ``usage.jsonl``. Never raises on I/O failure.

    Each record:
        {
            "ts": "<ISO8601 UTC>",
            "epoch": <float seconds>,
            "provider": "anthropic",
            "model": "anthropic/claude-sonnet-4-6",
            "input_tokens":  1234,
            "output_tokens":  567,
            "cost_usd":       0.0421,
        }
    """
    record = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "epoch": time.time(),
        "provider": provider,
        "model": model,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "cost_usd": _estimate_cost_usd(provider, model, input_tokens, output_tokens),
    }

    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    path = _usage_path()

    def _append() -> None:
        # Append is atomic for small writes on Windows NTFS and POSIX when under
        # PIPE_BUF / 4KiB. Our records are ~150 bytes; safe.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)

    try:
        await asyncio.to_thread(_append)
    except OSError as exc:
        logger.error(f"Cost: failed to append usage record to {path}: {exc}")


# ---------------------------------------------------------------------------
# Rollups
# ---------------------------------------------------------------------------


_WINDOW_SECONDS: Final[dict[str, float]] = {
    "hour": 3600.0,
    "day": 86400.0,
    "month": 30 * 86400.0,  # Approximate — Sandbox UI displays "this month" roughly.
}


async def get_usage_rollup(window: Literal["hour", "day", "month"]) -> dict[str, Any]:
    """Aggregate usage in the trailing ``window``.

    Returns a dict of the form::

        {
            "window": "day",
            "since": "2026-04-16T00:00:00Z",
            "total_cost_usd": 0.87,
            "providers": {
                "anthropic": {
                    "input_tokens": 12345,
                    "output_tokens": 6789,
                    "cost_usd": 0.71,
                    "calls": 14,
                },
                "ollama": { ... "cost_usd": 0.0, ... },
            },
        }

    Missing or unreadable ``usage.jsonl`` yields an empty-but-valid rollup.
    """
    if window not in _WINDOW_SECONDS:
        raise ValueError(f"unknown window '{window}' (expected one of {list(_WINDOW_SECONDS)})")

    since_epoch = time.time() - _WINDOW_SECONDS[window]
    since_iso = datetime.fromtimestamp(since_epoch, tz=UTC).isoformat(timespec="seconds")

    records = await _read_usage_since(since_epoch)

    by_provider: dict[str, dict[str, Any]] = {}
    total = 0.0
    for rec in records:
        provider = str(rec.get("provider") or "unknown")
        slot = by_provider.setdefault(
            provider,
            {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0},
        )
        slot["input_tokens"] += int(rec.get("input_tokens") or 0)
        slot["output_tokens"] += int(rec.get("output_tokens") or 0)
        cost = float(rec.get("cost_usd") or 0.0)
        slot["cost_usd"] += cost
        slot["calls"] += 1
        total += cost

    # Round to cents-scale so the UI doesn't show floating-point noise.
    total = round(total, 6)
    for slot in by_provider.values():
        slot["cost_usd"] = round(slot["cost_usd"], 6)

    return {
        "window": window,
        "since": since_iso,
        "total_cost_usd": total,
        "providers": by_provider,
    }


async def _read_usage_since(since_epoch: float) -> list[dict[str, Any]]:
    """Read and parse usage records newer than ``since_epoch``. Bad lines are skipped."""
    path = _usage_path()
    if not path.exists():
        return []

    def _scan() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        # Corrupt line — skip rather than fail the whole rollup.
                        continue
                    ts = float(rec.get("epoch") or 0.0)
                    if ts >= since_epoch:
                        out.append(rec)
        except OSError as exc:
            logger.error(f"Cost: failed to read usage log at {path}: {exc}")
            return []
        return out

    return await asyncio.to_thread(_scan)


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


async def set_budget(provider: str, daily_usd: float) -> None:
    """Persist a soft daily budget for ``provider``. Overwrites any existing value.

    Setting ``daily_usd <= 0`` removes the budget for this provider.
    """
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be a non-empty string")
    if daily_usd != daily_usd:  # NaN check
        raise ValueError("daily_usd must be a real number")

    key = provider.strip().lower()
    path = _budgets_path()

    def _write() -> None:
        data = _load_budgets_sync(path)
        if daily_usd <= 0:
            data.pop(key, None)
        else:
            data[key] = float(daily_usd)
        _atomic_write_json(path, data)

    await asyncio.to_thread(_write)
    logger.info(f"Cost: budget for '{key}' set to ${daily_usd:.2f}/day")


async def check_budget(provider: str) -> tuple[bool, float]:
    """Return ``(within_budget, spent_today_usd)`` for ``provider``.

    ``within_budget`` is ``True`` when:
      * no budget has been set for this provider, OR
      * today's spend is strictly less than the daily budget.

    Spend is the sum of ``cost_usd`` in records whose ``epoch`` lies in the
    current UTC day. (We use UTC to keep this simple and timezone-safe; the UI
    can present it in local time when rendering.)
    """
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be a non-empty string")
    key = provider.strip().lower()

    path = _budgets_path()
    budgets = await asyncio.to_thread(_load_budgets_sync, path)
    daily_limit = budgets.get(key)

    today_start = _utc_day_start_epoch()
    records = await _read_usage_since(today_start)
    spent = 0.0
    for rec in records:
        if str(rec.get("provider") or "").lower() == key:
            spent += float(rec.get("cost_usd") or 0.0)
    spent = round(spent, 6)

    if daily_limit is None:
        return True, spent
    return spent < float(daily_limit), spent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_day_start_epoch() -> float:
    now = datetime.now(UTC)
    start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    return start.timestamp()


def _load_budgets_sync(path: Path) -> dict[str, float]:
    """Load budgets.json; return empty dict if missing or corrupt."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(f"Cost: failed to load budgets at {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in data.items():
        try:
            out[str(k).lower()] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write ``data`` atomically: temp-file + replace. Prevents torn writes on crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, separators=(",", ":"), ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except OSError:
        # Best-effort cleanup; re-raise so callers know the write failed.
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


# ---------------------------------------------------------------------------
# One-shot helpers for the common call site: track usage coming off a Chunk
# ---------------------------------------------------------------------------


async def track_from_usage_dict(
    provider: str,
    model: str,
    usage: dict[str, int] | None,
) -> None:
    """Convenience wrapper: no-op if ``usage`` is ``None``.

    Typical call site, in the streaming loop::

        async for chunk in call_with_fallback(messages, Tier.MAIN):
            if chunk.content:
                send_to_client(chunk.content)
            if chunk.usage is not None:
                await track_from_usage_dict(provider, model, chunk.usage)
    """
    if usage is None:
        return
    await track_usage(
        provider=provider,
        model=model,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
    )
