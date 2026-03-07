"""Tests for graceful shutdown module."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.shutdown import _shutdown_event, is_shutting_down


class TestShutdownState:
    """Test shutdown state tracking."""

    def setup_method(self):
        _shutdown_event.clear()

    def test_not_shutting_down_initially(self):
        assert is_shutting_down() is False

    def test_shutting_down_after_event_set(self):
        _shutdown_event.set()
        assert is_shutting_down() is True

    def test_clear_resets_state(self):
        _shutdown_event.set()
        assert is_shutting_down() is True
        _shutdown_event.clear()
        assert is_shutting_down() is False


class TestShutdownSequence:
    """Test the shutdown sequence."""

    def setup_method(self):
        _shutdown_event.clear()

    @pytest.mark.asyncio
    async def test_shutdown_sequence_runs(self):
        from src.core.shutdown import _shutdown_sequence

        with (
            patch("src.core.shutdown.logger") as mock_logger,
        ):
            await _shutdown_sequence()
            assert is_shutting_down() is True
            mock_logger.info.assert_any_call("Shutdown: beginning graceful shutdown...")

    @pytest.mark.asyncio
    async def test_shutdown_sequence_idempotent(self):
        from src.core.shutdown import _shutdown_sequence

        _shutdown_event.set()
        with patch("src.core.shutdown.logger") as mock_logger:
            await _shutdown_sequence()
            # Should return immediately without logging "beginning" again
            for call in mock_logger.info.call_args_list:
                assert "beginning graceful shutdown" not in str(call)


class TestRegisterHandlers:
    """Test signal handler registration."""

    def setup_method(self):
        _shutdown_event.clear()

    def test_register_handlers_logs(self):
        from src.core.shutdown import register_shutdown_handlers

        loop = MagicMock()
        loop.add_signal_handler.side_effect = NotImplementedError
        with (
            patch("src.core.shutdown.signal"),
            patch("src.core.shutdown.logger") as mock_logger,
        ):
            register_shutdown_handlers(loop)
            mock_logger.info.assert_called_with("Shutdown: signal handlers registered")
