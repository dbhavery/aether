"""Module 05 tests — verify tool registry and dispatch."""

import pytest

from src.tools.dispatcher import TOOL_REGISTRY, dispatch_tool


class TestToolRegistry:
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

    def test_all_tools_are_callable(self):
        for name, fn in TOOL_REGISTRY.items():
            assert callable(fn), f"{name} is not callable"


class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        result = await dispatch_tool("nonexistent_tool", {})
        assert "Unknown tool" in result or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_list_running_apps_returns_success(self):
        from src.tools.pc_control import list_running_apps

        result = await list_running_apps()
        assert result["success"] is True
        assert isinstance(result["apps"], list)
