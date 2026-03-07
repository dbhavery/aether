"""Tests for process watchdog — health checks, duplicate detection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWatchdogHealth:
    """Test health check function."""

    @pytest.mark.asyncio
    async def test_healthy_server(self):
        from src.core.watchdog import check_health

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.core.watchdog.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            result = await check_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_unhealthy_server(self):
        from src.core.watchdog import check_health

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionRefusedError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.core.watchdog.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            result = await check_health()
            assert result is False


class TestDuplicateDetection:
    """Test duplicate instance detection."""

    def test_not_running_when_port_closed(self):
        from src.core.watchdog import is_already_running

        with patch("socket.socket") as mock_socket:
            instance = MagicMock()
            instance.connect.side_effect = ConnectionRefusedError("refused")
            instance.__enter__ = MagicMock(return_value=instance)
            instance.__exit__ = MagicMock(return_value=False)
            mock_socket.return_value = instance
            assert is_already_running() is False

    def test_running_when_port_open(self):
        from src.core.watchdog import is_already_running

        with patch("socket.socket") as mock_socket:
            instance = MagicMock()
            instance.connect.return_value = None  # success
            instance.__enter__ = MagicMock(return_value=instance)
            instance.__exit__ = MagicMock(return_value=False)
            mock_socket.return_value = instance
            assert is_already_running() is True


class TestCrashNotification:
    """Test crash notification."""

    def test_notify_crash_with_winotify(self):
        from src.core.watchdog import _notify_crash

        mock_notif_class = MagicMock()
        mock_instance = MagicMock()
        mock_notif_class.return_value = mock_instance
        mock_winotify = MagicMock()
        mock_winotify.Notification = mock_notif_class
        with patch.dict("sys.modules", {"winotify": mock_winotify}):
            _notify_crash(1)
            mock_instance.show.assert_called_once()

    def test_notify_crash_handles_import_error(self):
        from src.core.watchdog import _notify_crash

        # Should not raise even if winotify is broken
        with patch.dict("sys.modules", {"winotify": None}):
            _notify_crash(1)  # Should silently pass
