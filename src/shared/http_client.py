"""Shared aiohttp ClientSession — one session for the entire app lifetime.

Avoids connection churn from creating a new session per request.
"""

import asyncio

import aiohttp
from loguru import logger

_session: aiohttp.ClientSession | None = None
_session_lock: asyncio.Lock | None = None


def _get_session_lock() -> asyncio.Lock:
    """Lazily create asyncio.Lock inside the running event loop."""
    global _session_lock
    if _session_lock is None:
        _session_lock = asyncio.Lock()
    return _session_lock


async def get_shared_session() -> aiohttp.ClientSession:
    """Return the shared HTTP session, creating it lazily if needed."""
    global _session
    if _session is not None and not _session.closed:
        return _session
    async with _get_session_lock():
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=aiohttp.TCPConnector(limit=20),
            )
            logger.debug("HTTP: shared session created")
        return _session


async def close_shared_session() -> None:
    """Close the shared session (call during shutdown)."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None
        logger.info("HTTP: shared session closed")
