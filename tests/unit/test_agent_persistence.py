"""Tests for Batch 14 — agent task persistence with SQLite."""

import pytest

from src.agents.base import AgentStatus, AgentTask


class TestTaskRegistry:
    @pytest.mark.asyncio
    async def test_register_and_retrieve(self):
        from src.agents.task_registry import get_task_summary, register_task

        task = AgentTask(
            task_id="test-001",
            agent_name="research",
            instruction="Test research task",
            status=AgentStatus.PENDING,
        )
        await register_task(task)
        summary = get_task_summary()
        found = [t for t in summary if t["task_id"] == "test-001"]
        assert len(found) == 1
        assert found[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_update_task_status(self):
        from src.agents.task_registry import get_task_summary, register_task, update_task

        task = AgentTask(
            task_id="test-002",
            agent_name="writing",
            instruction="Test writing task",
            status=AgentStatus.RUNNING,
        )
        await register_task(task)
        await update_task("test-002", AgentStatus.COMPLETE, result="Done!")
        summary = get_task_summary()
        found = [t for t in summary if t["task_id"] == "test-002"]
        assert len(found) == 1
        assert found[0]["status"] == "complete"

    @pytest.mark.asyncio
    async def test_update_task_with_error(self):
        from src.agents.task_registry import get_task_summary, register_task, update_task

        task = AgentTask(
            task_id="test-003",
            agent_name="research",
            instruction="Failing task",
            status=AgentStatus.RUNNING,
        )
        await register_task(task)
        await update_task("test-003", AgentStatus.FAILED, error="Connection timeout")
        summary = get_task_summary()
        found = [t for t in summary if t["task_id"] == "test-003"]
        assert len(found) == 1
        assert found[0]["status"] == "failed"
        assert found[0]["error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_get_running_tasks(self):
        from src.agents.task_registry import get_running_tasks, register_task

        task = AgentTask(
            task_id="test-004",
            agent_name="research",
            instruction="Running task",
            status=AgentStatus.RUNNING,
        )
        await register_task(task)
        running = await get_running_tasks()
        ids = [t.task_id for t in running]
        assert "test-004" in ids

    @pytest.mark.asyncio
    async def test_clear_completed(self):
        from src.agents.task_registry import clear_completed_tasks, register_task, update_task

        task = AgentTask(
            task_id="test-005",
            agent_name="writing",
            instruction="Will complete",
            status=AgentStatus.RUNNING,
        )
        await register_task(task)
        await update_task("test-005", AgentStatus.COMPLETE, result="Done")
        removed = clear_completed_tasks()
        assert removed >= 1

    @pytest.mark.asyncio
    async def test_mark_stale_running_as_failed(self):
        from src.agents.task_registry import (
            get_task_summary,
            mark_stale_running_as_failed,
            register_task,
        )

        task = AgentTask(
            task_id="test-006",
            agent_name="research",
            instruction="Stale running task",
            status=AgentStatus.RUNNING,
        )
        await register_task(task)
        count = await mark_stale_running_as_failed()
        assert count >= 1
        summary = get_task_summary()
        found = [t for t in summary if t["task_id"] == "test-006"]
        assert found[0]["status"] == "failed"
        assert "restarted" in found[0]["error"].lower()

    def test_task_summary_returns_list(self):
        from src.agents.task_registry import get_task_summary

        result = get_task_summary()
        assert isinstance(result, list)


class TestAgentBase:
    def test_agent_status_values(self):
        assert AgentStatus.PENDING == "pending"
        assert AgentStatus.RUNNING == "running"
        assert AgentStatus.COMPLETE == "complete"
        assert AgentStatus.FAILED == "failed"

    def test_agent_task_creation(self):
        task = AgentTask(
            task_id="t1",
            agent_name="test",
            instruction="do something",
        )
        assert task.status == AgentStatus.PENDING
        assert task.result is None
        assert task.error is None
        assert task.metadata == {}
