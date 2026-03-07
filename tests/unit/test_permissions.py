"""Tests for permissions system, audit log, and window management tools."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from src.tools.approval_gate import ActionRisk
from src.tools.permissions import (
    check_permission,
    get_allowed_apps,
    get_blocked_commands,
    get_blocked_paths,
    is_command_blocked,
    is_path_blocked,
)


class TestPermissions:
    def test_blocked_paths_returns_list(self):
        paths = get_blocked_paths()
        assert isinstance(paths, list)
        assert ".ssh" in paths

    def test_blocked_commands_returns_list(self):
        cmds = get_blocked_commands()
        assert isinstance(cmds, list)
        assert "rm -rf" in cmds

    def test_is_path_blocked_ssh(self):
        assert is_path_blocked("C:\\Users\\testuser\\.ssh\\id_rsa") is True

    def test_is_path_blocked_safe(self):
        assert is_path_blocked("C:\\Users\\testuser\\Documents\\notes.txt") is False

    def test_is_command_blocked_rm_rf(self):
        assert is_command_blocked("rm -rf /") is True

    def test_is_command_blocked_safe(self):
        assert is_command_blocked("dir C:\\Users") is False

    def test_check_permission_read_safe_file(self):
        risk, denied = check_permission("read_file", "C:\\Users\\testuser\\Documents\\hello.txt")
        assert risk == ActionRisk.SAFE
        assert denied is False

    def test_check_permission_read_blocked_file(self):
        risk, denied = check_permission("read_file", "C:\\Users\\testuser\\.ssh\\id_rsa")
        assert risk == ActionRisk.EXPLICIT
        assert denied is True  # Hard DENY — blocked path

    def test_check_permission_write_file_confirm(self):
        # Must mock writable check since test machine may differ
        with patch("src.tools.permissions.is_path_writable", return_value=True):
            risk, denied = check_permission("write_to_file", "./data/test.txt")
        assert risk == ActionRisk.CONFIRM
        assert denied is False

    def test_check_permission_write_blocked_path(self):
        risk, denied = check_permission("write_to_file", "C:\\Users\\testuser\\.env")
        assert risk == ActionRisk.EXPLICIT
        assert denied is True  # Hard DENY — blocked path

    def test_check_permission_run_command_confirm(self):
        risk, denied = check_permission("run_command", "dir C:\\")
        assert risk == ActionRisk.CONFIRM
        assert denied is False

    def test_check_permission_run_blocked_command(self):
        risk, denied = check_permission("run_command", "rm -rf /")
        assert risk == ActionRisk.EXPLICIT
        assert denied is True  # Hard DENY — blocked command

    def test_check_permission_screenshot_safe(self):
        risk, denied = check_permission("take_screenshot")
        assert risk == ActionRisk.SAFE
        assert denied is False

    def test_check_permission_close_window_confirm(self):
        risk, denied = check_permission("close_window", "Notepad")
        assert risk == ActionRisk.CONFIRM
        assert denied is False

    def test_check_permission_minimize_safe(self):
        risk, denied = check_permission("minimize_window", "Notepad")
        assert risk == ActionRisk.SAFE
        assert denied is False

    def test_check_permission_unknown_action_confirm(self):
        risk, denied = check_permission("some_new_action", "target")
        assert risk == ActionRisk.CONFIRM
        assert denied is False

    def test_allowed_apps_from_config(self):
        apps = get_allowed_apps()
        assert isinstance(apps, list)
        assert "notepad" in apps


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_log_tool_execution_writes_jsonl(self):
        from src.tools.audit_log import _get_log_path, log_tool_execution

        # Use today's log path
        log_path = _get_log_path()

        await log_tool_execution(
            tool_name="test_tool",
            args={"key": "value"},
            result="{'success': True}",
            execution_time_ms=42.5,
        )

        assert log_path.exists()
        # Read last line
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        last_entry = json.loads(lines[-1])
        assert last_entry["tool_name"] == "test_tool"
        assert last_entry["execution_time_ms"] == 42.5
        assert last_entry["user_approved"] is True

    def test_sanitize_args_redacts_sensitive(self):
        from src.tools.audit_log import _sanitize_args

        args = {"command": "ls", "api_key": "sk-12345", "password": "secret123"}
        sanitized = _sanitize_args(args)
        assert sanitized["command"] == "ls"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["password"] == "[REDACTED]"  # noqa: S105 — test verifies redaction

    def test_sanitize_args_truncates_long_values(self):
        from src.tools.audit_log import _sanitize_args

        args = {"content": "x" * 2000}
        sanitized = _sanitize_args(args)
        assert len(sanitized["content"]) < 2000
        assert "2000 chars total" in sanitized["content"]

    def test_audit_timer(self):
        import time

        from src.tools.audit_log import AuditTimer

        with AuditTimer() as timer:
            time.sleep(0.01)
        assert timer.elapsed_ms > 5  # At least 5ms

    def test_cleanup_old_logs(self):
        from src.tools.audit_log import cleanup_old_logs

        # Just verify it runs without error
        removed = cleanup_old_logs()
        assert isinstance(removed, int)

    def test_get_log_path_uses_date(self):
        from src.tools.audit_log import _get_log_path

        path = _get_log_path(datetime(2026, 1, 15))
        assert "tool_log_2026-01-15.jsonl" in str(path)


class TestWindowManagement:
    def test_minimize_window_in_registry(self):
        from src.tools.dispatcher import TOOL_REGISTRY

        assert "minimize_window" in TOOL_REGISTRY

    def test_maximize_window_in_registry(self):
        from src.tools.dispatcher import TOOL_REGISTRY

        assert "maximize_window" in TOOL_REGISTRY

    def test_close_window_in_registry(self):
        from src.tools.dispatcher import TOOL_REGISTRY

        assert "close_window" in TOOL_REGISTRY

    def test_tool_definitions_include_window_tools(self):
        from src.tools.dispatcher import TOOL_DEFINITIONS

        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert "minimize_window" in names
        assert "maximize_window" in names
        assert "close_window" in names

    def test_close_window_requires_confirm(self):
        from src.tools.approval_gate import HIGH_IMPACT_ACTIONS, ActionRisk

        assert HIGH_IMPACT_ACTIONS.get("close_window") == ActionRisk.CONFIRM

    def test_minimize_maximize_are_safe(self):
        from src.tools.approval_gate import HIGH_IMPACT_ACTIONS, ActionRisk

        assert HIGH_IMPACT_ACTIONS.get("minimize_window") == ActionRisk.SAFE
        assert HIGH_IMPACT_ACTIONS.get("maximize_window") == ActionRisk.SAFE
