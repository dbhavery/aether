"""Tests for shared HTTP client singleton."""

import pytest

from src.shared.http_client import close_shared_session, get_shared_session


class TestSharedSession:
    """Test the shared aiohttp session."""

    @pytest.mark.asyncio
    async def test_get_session_returns_session(self):
        import src.shared.http_client as mod

        mod._session = None
        session = await get_shared_session()
        assert session is not None
        assert not session.closed
        # Cleanup
        await close_shared_session()

    @pytest.mark.asyncio
    async def test_get_session_returns_same_instance(self):
        import src.shared.http_client as mod

        mod._session = None
        s1 = await get_shared_session()
        s2 = await get_shared_session()
        assert s1 is s2
        await close_shared_session()

    @pytest.mark.asyncio
    async def test_close_session(self):
        import src.shared.http_client as mod

        mod._session = None
        session = await get_shared_session()
        assert not session.closed
        await close_shared_session()
        assert mod._session is None

    @pytest.mark.asyncio
    async def test_close_when_no_session(self):
        import src.shared.http_client as mod

        mod._session = None
        await close_shared_session()  # Should not raise

    @pytest.mark.asyncio
    async def test_get_new_session_after_close(self):
        import src.shared.http_client as mod

        mod._session = None
        s1 = await get_shared_session()
        await close_shared_session()
        s2 = await get_shared_session()
        assert s1 is not s2
        await close_shared_session()
