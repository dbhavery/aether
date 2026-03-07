"""Module 06 tests — verify avatar client behavior."""

from unittest.mock import AsyncMock

import pytest


class TestAvatarClient:
    @pytest.mark.asyncio
    async def test_unavailable_when_liveportrait_down(self):
        """Avatar client gracefully handles LivePortrait being unavailable."""
        from src.avatar.client import AvatarClient

        client = AvatarClient()
        # Mock the persistent session to raise connection error on .get()
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.get = AsyncMock(side_effect=Exception("connection refused"))
        client._session = mock_session
        available = await client.check_health()
        assert available is False
        assert client.available is False

    @pytest.mark.asyncio
    async def test_set_speaking_noop_when_unavailable(self):
        """set_speaking is fire-and-forget — never raises when unavailable."""
        from src.avatar.client import AvatarClient

        client = AvatarClient()
        client._available = False
        await client.set_speaking(True)  # Should not raise

    def test_stream_url_from_config(self):
        """Stream URL is read from config and contains port 8770."""
        from src.avatar.client import AvatarClient

        client = AvatarClient()
        assert "8770" in client.stream_url

    def test_default_enabled(self):
        """Avatar is enabled by default."""
        from src.avatar.client import AvatarClient

        client = AvatarClient()
        assert client._enabled is True
