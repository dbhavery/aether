"""Unit tests for avatar server launcher (src/avatar/server.py)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestAvatarServerLauncher:
    """Tests for the avatar server launcher module."""

    def test_personalive_paths_defined(self):
        """Verify PersonaLive paths are resolved correctly from config."""
        from src.avatar.server import _get_avatar_paths

        paths = _get_avatar_paths()
        assert paths["personalive_server"] == paths["personalive_dir"] / "aether_server.py"
        assert paths["personalive_python"] == paths["personalive_dir"] / ".venv" / "Scripts" / "python.exe"

    def test_health_url_correct(self):
        from src.avatar.server import HEALTH_URL

        assert HEALTH_URL == "http://localhost:8770/health"

    @pytest.mark.asyncio
    async def test_start_returns_none_when_no_backends(self):
        """When neither PersonaLive nor LivePortrait exist, returns 'none'."""
        fake_paths = {
            "personalive_dir": Path("/nonexistent"),
            "personalive_server": Path("/nonexistent/server.py"),
            "personalive_python": Path("/nonexistent/python.exe"),
            "liveportrait_dir": Path("/nonexistent"),
            "liveportrait_server": Path("/nonexistent/server.py"),
            "liveportrait_python": Path("/nonexistent/python.exe"),
        }
        with patch("src.avatar.server._get_avatar_paths", return_value=fake_paths):
            from src.avatar.server import start_avatar_server

            result = await start_avatar_server()
            assert result == "none"

    @pytest.mark.asyncio
    async def test_wait_for_health_timeout(self):
        """_wait_for_health returns False on timeout when server unreachable."""
        from src.avatar.server import _wait_for_health

        # Mock httpx to always raise connection error
        with patch("src.avatar.server.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = ConnectionError("no server")
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance
            result = await _wait_for_health(1)
            assert result is False

    @pytest.mark.asyncio
    async def test_get_engine_name_fallback(self):
        """_get_engine_name returns 'unknown' when health check fails."""
        from src.avatar.server import _get_engine_name

        result = await _get_engine_name()
        assert result == "unknown"
