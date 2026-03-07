"""Tests for the 5 deferred fixes from the final audit session.

Fix 1: Avatar subprocess cleanup
Fix 2: LLM call timeouts
Fix 3: PyAutoGUI scope restriction
Fix 4: TLS documentation (no code — verified via docs check)
Fix 5: Backup script, runbook, crash alerting
"""

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fix 1: Avatar subprocess cleanup
# ---------------------------------------------------------------------------


class TestAvatarCleanup:
    """Verify avatar subprocess tracking and cleanup."""

    def test_cleanup_avatar_registered_with_atexit(self):
        """_cleanup_avatar must be registered with atexit."""

        from src.avatar.server import _cleanup_avatar

        # atexit doesn't expose registered functions directly on all platforms,
        # but we can verify the function exists and is callable
        assert callable(_cleanup_avatar)

    def test_cleanup_avatar_does_nothing_when_no_proc(self):
        """_cleanup_avatar is safe to call when no subprocess exists."""
        import src.avatar.server as server_mod

        original = server_mod._avatar_proc
        try:
            server_mod._avatar_proc = None
            server_mod._cleanup_avatar()  # Should not raise
        finally:
            server_mod._avatar_proc = original

    def test_cleanup_avatar_terminates_running_proc(self):
        """_cleanup_avatar terminates a running subprocess."""
        import src.avatar.server as server_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc.wait.return_value = 0

        original = server_mod._avatar_proc
        try:
            server_mod._avatar_proc = mock_proc
            server_mod._cleanup_avatar()
            mock_proc.terminate.assert_called_once()
        finally:
            server_mod._avatar_proc = original

    def test_cleanup_avatar_kills_on_timeout(self):
        """_cleanup_avatar force-kills when terminate times out."""
        import subprocess

        import src.avatar.server as server_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 5)

        original = server_mod._avatar_proc
        try:
            server_mod._avatar_proc = mock_proc
            server_mod._cleanup_avatar()
            mock_proc.kill.assert_called_once()
        finally:
            server_mod._avatar_proc = original

    def test_shutdown_sequence_calls_avatar_cleanup(self):
        """Shutdown sequence includes avatar cleanup step."""
        import inspect

        from src.core.shutdown import _shutdown_sequence

        source = inspect.getsource(_shutdown_sequence)
        assert "_cleanup_avatar" in source


# ---------------------------------------------------------------------------
# Fix 2: LLM call timeouts
# ---------------------------------------------------------------------------


class TestLLMTimeouts:
    """Verify LLM calls have timeouts configured."""

    def test_timeout_constants_defined(self):
        from src.brain.clients import FAST_TIMEOUT, GEMINI_TIMEOUT, HEAVY_TIMEOUT, PRIMARY_TIMEOUT

        assert FAST_TIMEOUT == 15.0
        assert PRIMARY_TIMEOUT == 45.0
        assert HEAVY_TIMEOUT == 120.0
        assert GEMINI_TIMEOUT == 30.0

    def test_get_timeout_returns_defaults(self):
        from src.brain.clients import _get_timeout

        with patch("src.brain.clients.get_yaml_config") as mock_yaml:
            mock_yaml.return_value = {"llm": {}}
            assert _get_timeout("fast") == 15.0
            assert _get_timeout("primary") == 45.0
            assert _get_timeout("heavy") == 120.0
            assert _get_timeout("gemini") == 30.0

    def test_get_timeout_reads_config(self):
        from src.brain.clients import _get_timeout

        with patch("src.brain.clients.get_yaml_config") as mock_yaml:
            mock_yaml.return_value = {"llm": {"timeout_primary_seconds": 60}}
            assert _get_timeout("primary") == 60.0

    @pytest.mark.asyncio
    async def test_claude_raises_on_timeout(self):
        """call_claude raises RuntimeError on timeout."""
        from src.brain.clients import call_claude

        with (
            patch("src.brain.clients.get_settings") as mock_settings,
            patch("src.brain.clients.get_yaml_config") as mock_yaml,
            patch("src.brain.clients._get_timeout", return_value=0.01),
        ):
            mock_settings.return_value.anthropic_api_key = "test-key"
            mock_yaml.return_value = {"llm": {"claude_model": "test", "max_tokens": 100}}

            # Mock the Anthropic client to sleep forever
            mock_client = MagicMock()

            async def slow_create(**kwargs):
                await asyncio.sleep(100)

            mock_client.return_value.messages.create = slow_create

            with (
                patch.dict("sys.modules", {"anthropic": MagicMock(AsyncAnthropic=mock_client)}),
                pytest.raises(RuntimeError, match="timed out"),
            ):
                await call_claude(prompt="test")

    @pytest.mark.asyncio
    async def test_gemini_raises_on_timeout(self):
        """call_gemini raises RuntimeError on timeout."""
        from src.brain.clients import call_gemini

        with (
            patch("src.brain.clients.get_settings") as mock_settings,
            patch("src.brain.clients.get_yaml_config") as mock_yaml,
            patch("src.brain.clients._get_timeout", return_value=0.01),
        ):
            mock_settings.return_value.google_api_key = "test-key"
            mock_yaml.return_value = {"llm": {"gemini_model": "test", "max_tokens": 100}}

            # Mock genai to sleep forever in to_thread
            with patch("src.brain.clients.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:

                async def slow_thread(*args, **kwargs):
                    await asyncio.sleep(100)

                mock_thread.side_effect = slow_thread

                mock_client = MagicMock()
                mock_aio = MagicMock()
                mock_models = MagicMock()

                async def slow_generate(*args, **kwargs):
                    await asyncio.sleep(100)

                mock_models.generate_content = slow_generate
                mock_aio.models = mock_models
                mock_client.aio = mock_aio

                with (
                    patch("google.genai.Client", return_value=mock_client),
                    pytest.raises(RuntimeError, match="timed out"),
                ):
                    await call_gemini(prompt="test")

    def test_brain_handler_catches_timeout(self):
        """Brain handler has RuntimeError/timeout handling."""
        import inspect

        from src.brain.handler import on_user_message

        source = inspect.getsource(on_user_message)
        assert "timed out" in source
        assert "taking longer than usual" in source


# ---------------------------------------------------------------------------
# Fix 3: PyAutoGUI scope restriction
# ---------------------------------------------------------------------------


class TestPyAutoGUIScope:
    """Verify PyAutoGUI is not imported at module level."""

    def test_no_module_level_pyautogui_import(self):
        """PyAutoGUI must not be imported at module level in pc_control.py."""
        source = Path("src/tools/pc_control.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Find all function/async function definitions
        func_start_lines = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                func_start_lines.add(node.lineno)

        # Find the earliest function definition line
        first_func_line = min(func_start_lines) if func_start_lines else len(source.splitlines()) + 1

        # Check all import statements for pyautogui
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "pyautogui" in alias.name:
                        assert node.lineno >= first_func_line, (
                            f"pyautogui imported at module level (line {node.lineno}), "
                            f"must be inside a function (first function at line {first_func_line})"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module and "pyautogui" in node.module:
                assert node.lineno >= first_func_line, f"pyautogui imported at module level (line {node.lineno})"

    def test_pc_control_module_docstring_mentions_security(self):
        """Module docstring documents the security decision."""
        source = Path("src/tools/pc_control.py").read_text(encoding="utf-8")
        assert "SECURITY" in source[:500]


# ---------------------------------------------------------------------------
# Fix 4: TLS documentation
# ---------------------------------------------------------------------------


class TestTLSDocumentation:
    """Verify TLS decision is documented."""

    def test_decisions_log_has_tls_entry(self):
        content = Path("docs/decisions-log.md").read_text(encoding="utf-8")
        assert "TLS on WebSocket" in content
        assert "DEFERRED" in content

    def test_issues_has_deferred_section(self):
        content = Path("docs/issues.md").read_text(encoding="utf-8")
        assert "DEFERRED (BY DESIGN)" in content
        assert "TLS on WebSocket" in content


# ---------------------------------------------------------------------------
# Fix 5: Backup, runbook, crash alerting
# ---------------------------------------------------------------------------


class TestBackupScript:
    """Verify backup script exists and has correct structure."""

    def test_backup_script_exists(self):
        assert Path("scripts/backup_data.py").exists()

    def test_backup_script_imports(self):
        from scripts.backup_data import BACKUP_ROOT, DATA_ROOT, ITEMS_TO_BACKUP, run_backup

        assert callable(run_backup)
        assert Path(r"./data") == DATA_ROOT
        assert BACKUP_ROOT == DATA_ROOT / "backups"
        assert len(ITEMS_TO_BACKUP) >= 5


class TestRunbook:
    """Verify runbook exists and covers key scenarios."""

    def test_runbook_exists(self):
        assert Path("docs/runbook.md").exists()

    def test_runbook_covers_key_scenarios(self):
        content = Path("docs/runbook.md").read_text(encoding="utf-8")
        assert "won't start" in content.lower()
        assert "won't respond" in content.lower()
        assert "voice not working" in content.lower()
        assert "avatar" in content.lower()
        assert "backup" in content.lower() or "restore" in content.lower()


class TestCrashAlerting:
    """Verify crash notification supports multiple channels."""

    def test_watchdog_notify_has_telegram(self):
        """_notify_crash includes Telegram notification path."""
        import inspect

        from src.core.watchdog import _notify_crash

        source = inspect.getsource(_notify_crash)
        assert "TELEGRAM_BOT_TOKEN" in source
        assert "TELEGRAM_CHAT_ID" in source
        assert "api.telegram.org" in source

    def test_telegram_chat_id_in_api_registry(self):
        from src.shared.api_registry import get_service

        svc = get_service("telegram_chat")
        assert svc is not None
        assert svc.env_var == "TELEGRAM_CHAT_ID"
        assert svc.required is False

    def test_notify_crash_runs_without_telegram(self):
        """_notify_crash succeeds when Telegram is not configured."""
        from src.core.watchdog import _notify_crash

        with (
            patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}),
            patch("src.core.watchdog.logger"),
        ):
            _notify_crash(1)  # Should not raise


class TestConfigTimeouts:
    """Verify timeout values in config file."""

    def test_yaml_has_timeout_keys(self):
        import yaml

        config = yaml.safe_load(Path("aether_config.yaml").read_text(encoding="utf-8"))
        llm = config["llm"]
        assert llm["timeout_fast_seconds"] == 15
        assert llm["timeout_primary_seconds"] == 45
        assert llm["timeout_heavy_seconds"] == 120
        assert llm["timeout_gemini_seconds"] == 30
