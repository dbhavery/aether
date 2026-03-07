"""Tests for tool dispatcher — verifies registry, dispatch, and error handling."""

from unittest.mock import AsyncMock, patch

import pytest

from src.tools.dispatcher import TOOL_DEFINITIONS, TOOL_REGISTRY, dispatch_tool


class TestToolDispatcher:
    def test_registry_has_expected_tools(self):
        expected = {
            "open_application",
            "type_text",
            "get_clipboard",
            "take_screenshot",
            "list_running_apps",
            "focus_window",
            "get_active_window_title",
            "minimize_window",
            "maximize_window",
            "close_window",
            "read_file",
            "write_to_file",
            "list_directory",
            "search_files",
            "create_directory",
            "run_command",
        }
        assert set(TOOL_REGISTRY.keys()) == expected

    def test_tool_definitions_match_registry(self):
        definition_names = {t["name"] for t in TOOL_DEFINITIONS}
        assert definition_names == set(TOOL_REGISTRY.keys())

    def test_tool_definitions_have_required_fields(self):
        for tool_def in TOOL_DEFINITIONS:
            assert "name" in tool_def
            assert "description" in tool_def
            assert "input_schema" in tool_def
            assert tool_def["input_schema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool_returns_error(self):
        result = await dispatch_tool("nonexistent_tool", {})
        assert "not found" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_dispatch_list_running_apps(self):
        result = await dispatch_tool("list_running_apps", {})
        assert "success" in result.lower() or "apps" in result.lower()

    @pytest.mark.asyncio
    async def test_dispatch_rejects_invalid_args(self):
        """Extra args should be filtered out, not crash."""
        result = await dispatch_tool("list_running_apps", {"invalid_arg": "value"})
        assert "success" in result.lower()

    @pytest.mark.asyncio
    async def test_dispatch_tool_failure_returns_error_string(self):
        """If a tool raises, dispatcher returns error string instead of crashing."""
        with patch.dict(TOOL_REGISTRY, {"failing_tool": AsyncMock(side_effect=RuntimeError("boom"))}):
            result = await dispatch_tool("failing_tool", {})
            assert "error" in result.lower()
            # Error details are sanitized — exception message NOT leaked to LLM
            assert "check server logs" in result.lower()


class TestPathTraversal:
    @pytest.mark.asyncio
    async def test_screenshot_rejects_path_outside_allowed_dir(self):
        from src.tools.pc_control import take_screenshot

        result = await take_screenshot(save_path="C:\\Windows\\System32\\evil.png")
        assert result["success"] is False
        assert "save_path must be under" in result["error"]
