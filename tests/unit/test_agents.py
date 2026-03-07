"""Module 11 tests — verify agent dispatching and task registry."""

from unittest.mock import AsyncMock, patch

import pytest


class TestAgentBase:
    def test_agent_task_dataclass(self):
        from src.agents.base import AgentStatus, AgentTask

        task = AgentTask("t1", "test_agent", "do something")
        assert task.status == AgentStatus.PENDING
        assert task.result is None

    def test_agent_status_values(self):
        from src.agents.base import AgentStatus

        assert AgentStatus.PENDING.value == "pending"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.COMPLETE.value == "complete"
        assert AgentStatus.FAILED.value == "failed"


class TestTaskRegistry:
    @pytest.mark.asyncio
    async def test_register_and_retrieve(self):
        from src.agents.base import AgentTask
        from src.agents.task_registry import get_task_summary, register_task

        task = AgentTask("test_001", "test_agent", "test instruction")
        await register_task(task)
        summary = get_task_summary()
        assert any(t["task_id"] == "test_001" for t in summary)

    @pytest.mark.asyncio
    async def test_update_task_status(self):
        from src.agents.base import AgentStatus, AgentTask
        from src.agents.task_registry import get_task_summary, register_task, update_task

        task = AgentTask("test_002", "test_agent", "update test")
        await register_task(task)
        await update_task("test_002", AgentStatus.COMPLETE, result="done")
        summary = get_task_summary()
        t = next(t for t in summary if t["task_id"] == "test_002")
        assert t["status"] == "complete"

    @pytest.mark.asyncio
    async def test_clear_completed_tasks(self):
        from src.agents.base import AgentStatus, AgentTask
        from src.agents.task_registry import clear_completed_tasks, register_task, update_task

        task = AgentTask("test_003", "test_agent", "clear test")
        await register_task(task)
        await update_task("test_003", AgentStatus.COMPLETE, result="done")
        removed = clear_completed_tasks()
        assert removed >= 1


class TestDispatcher:
    @pytest.mark.asyncio
    async def test_unknown_intent_returns_gracefully(self):
        from src.agents.dispatcher import dispatch

        result = await dispatch("unknown_intent", "some payload")
        assert "don't have an agent" in result.lower()

    @pytest.mark.asyncio
    async def test_research_dispatch(self):
        with patch(
            "src.agents.research_agent.run_research", new_callable=AsyncMock, return_value="Research result here"
        ):
            from src.agents.dispatcher import dispatch

            result = await dispatch("research", "latest AI news")
            assert result == "Research result here"

    @pytest.mark.asyncio
    async def test_draft_email_dispatch(self):
        with patch("src.agents.writing_agent.draft_content", new_callable=AsyncMock, return_value="Dear Bob, ..."):
            from src.agents.dispatcher import dispatch

            result = await dispatch("draft_email", "thank Bob for lunch")
            assert result == "Dear Bob, ..."


class TestIntentDetection:
    def test_research_pattern(self):
        from src.brain.handler import _detect_agent_intent

        result = _detect_agent_intent("research the latest AI models")
        assert result is not None
        assert result[0] == "research"
        assert "latest AI models" in result[1]

    def test_draft_email_pattern(self):
        from src.brain.handler import _detect_agent_intent

        result = _detect_agent_intent("draft an email to Bob thanking him")
        assert result is not None
        assert result[0] == "draft_email"

    def test_no_match_returns_none(self):
        from src.brain.handler import _detect_agent_intent

        result = _detect_agent_intent("what's the weather like?")
        assert result is None

    def test_look_up_pattern(self):
        from src.brain.handler import _detect_agent_intent

        result = _detect_agent_intent("look up quantum computing breakthroughs")
        assert result is not None
        assert result[0] == "research"
