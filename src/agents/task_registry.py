"""Task registry — persists all agent tasks to SQLite.

Uses aiosqlite for async access. Tasks survive server restarts.
DB location: ./data/agent_tasks.db
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.agents.base import AgentStatus, AgentTask
from src.shared.config import get_settings

_db_path: str | None = None
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    """Lazily create asyncio.Lock inside the running event loop."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _get_db_path() -> str:
    """Lazily resolve DB path — avoids calling get_settings() at import time."""
    global _db_path
    if _db_path is None:
        _db_path = str(Path(get_settings().aether_data_path) / "agent_tasks.db")
    return _db_path


_initialized = False

# In-memory cache for fast reads
_tasks_cache: dict[str, AgentTask] = {}

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    instruction TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    error TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


async def _get_db():
    """Get aiosqlite connection."""
    import aiosqlite

    return await aiosqlite.connect(_get_db_path())


async def _ensure_initialized() -> None:
    """Create table if it doesn't exist."""
    global _initialized
    if _initialized:
        return

    async with _get_lock():
        if _initialized:
            return
        try:
            db = await _get_db()
            try:
                await db.execute(_CREATE_TABLE_SQL)
                await db.commit()
                _initialized = True
                logger.info(f"AgentRegistry: SQLite DB initialized at {_get_db_path()}")

                # Load existing tasks into cache
                async with db.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100") as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        try:
                            status = AgentStatus(row[3])
                        except ValueError:
                            logger.warning(f"AgentRegistry: skipping task {row[0]} — invalid status '{row[3]}'")
                            continue
                        try:
                            metadata = json.loads(row[6]) if row[6] else {}
                        except json.JSONDecodeError:
                            logger.warning(f"AgentRegistry: task {row[0]} has invalid metadata JSON, using empty")
                            metadata = {}
                        task = AgentTask(
                            task_id=row[0],
                            agent_name=row[1],
                            instruction=row[2],
                            status=status,
                            result=row[4],
                            error=row[5],
                            metadata=metadata,
                        )
                        _tasks_cache[task.task_id] = task
                    logger.info(f"AgentRegistry: loaded {len(rows)} tasks from DB")
            finally:
                await db.close()
        except ImportError:
            logger.warning("AgentRegistry: aiosqlite not available, using in-memory only")
            _initialized = True
        except Exception as e:
            logger.error(f"AgentRegistry: DB init failed: {e}")
            _initialized = True  # Don't retry on every call


async def register_task(task: AgentTask) -> None:
    """Register a new agent task — persists to SQLite and cache."""
    await _ensure_initialized()
    now = datetime.now().isoformat()

    async with _get_lock():
        try:
            db = await _get_db()
            try:
                await db.execute(
                    """INSERT OR REPLACE INTO tasks
                       (id, agent_name, instruction, status, result, error, metadata, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.task_id,
                        task.agent_name,
                        task.instruction,
                        task.status.value,
                        task.result,
                        task.error,
                        json.dumps(task.metadata),
                        now,
                        now,
                    ),
                )
                await db.commit()
            finally:
                await db.close()
            # Update cache AFTER successful DB commit
            _tasks_cache[task.task_id] = task
            logger.info(f"AgentRegistry: registered {task.agent_name} -- {task.task_id}")
        except ImportError:
            # No DB — cache-only is fine
            _tasks_cache[task.task_id] = task
            logger.debug("AgentRegistry: aiosqlite not available, in-memory only")
        except Exception as e:
            logger.error(f"AgentRegistry: failed to persist task: {e}")


async def update_task(
    task_id: str,
    status: AgentStatus,
    result: str | None = None,
    error: str | None = None,
) -> None:
    """Update a task's status — persists to SQLite and cache."""
    await _ensure_initialized()
    now = datetime.now().isoformat()

    async with _get_lock():
        try:
            db = await _get_db()
            try:
                await db.execute(
                    """UPDATE tasks SET status=?, result=COALESCE(?, result),
                       error=COALESCE(?, error), updated_at=? WHERE id=?""",
                    (status.value, result, error, now, task_id),
                )
                await db.commit()
            finally:
                await db.close()
        except ImportError:
            pass  # No DB — cache-only update below
        except Exception as e:
            logger.error(f"AgentRegistry: failed to update task {task_id}: {e}")
            return  # Don't update cache if DB write failed

        # Update cache AFTER successful DB commit (or if DB unavailable)
        if task_id in _tasks_cache:
            _tasks_cache[task_id].status = status
            if result is not None:
                _tasks_cache[task_id].result = result
            if error is not None:
                _tasks_cache[task_id].error = error


def get_task_summary() -> list[dict]:
    """Returns all tasks grouped by status. The user sees this in the task panel."""
    return [
        {
            "task_id": t.task_id,
            "agent": t.agent_name,
            "instruction": t.instruction[:80],
            "status": t.status.value,
            "result_preview": (t.result or "")[:100],
            "error": t.error,
        }
        for t in sorted(_tasks_cache.values(), key=lambda x: x.task_id, reverse=True)
    ]


async def get_running_tasks() -> list[AgentTask]:
    """Get all tasks with RUNNING status — used for resume on restart."""
    await _ensure_initialized()
    return [t for t in _tasks_cache.values() if t.status == AgentStatus.RUNNING]


async def get_pending_tasks() -> list[AgentTask]:
    """Get all tasks with PENDING status."""
    await _ensure_initialized()
    return [t for t in _tasks_cache.values() if t.status == AgentStatus.PENDING]


def clear_completed_tasks() -> int:
    """Remove completed/failed tasks from cache (DB retains history). Returns count removed."""
    to_remove = [tid for tid, t in _tasks_cache.items() if t.status in (AgentStatus.COMPLETE, AgentStatus.FAILED)]
    for tid in to_remove:
        del _tasks_cache[tid]
    return len(to_remove)


async def mark_stale_running_as_failed() -> int:
    """Mark any RUNNING tasks as FAILED (server restarted). Returns count updated."""
    await _ensure_initialized()
    running = await get_running_tasks()
    count = 0
    for task in running:
        await update_task(task.task_id, AgentStatus.FAILED, error="Server restarted — task interrupted")
        count += 1
    if count:
        logger.info(f"AgentRegistry: marked {count} stale RUNNING tasks as FAILED")
    return count
