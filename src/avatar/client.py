"""
Avatar client — thin connector between Aether server and LivePortrait API.
LivePortrait runs as a completely separate process. This module just talks to it.
"""

import aiohttp
from loguru import logger

from src.shared.config import get_yaml_config


class AvatarClient:
    """Connects to LivePortrait API to check health and control speaking state."""

    def __init__(self) -> None:
        config = get_yaml_config()
        avatar_cfg = config.get("avatar", {})
        self._base_url = avatar_cfg.get("liveportrait_url", "http://localhost:8770")
        self._stream_url = avatar_cfg.get("stream_url", "http://localhost:8770/stream")
        self._enabled = avatar_cfg.get("enabled", True)
        self._available = False
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return a persistent aiohttp session for this client, creating lazily."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5),
            )
            logger.debug("Avatar: persistent HTTP session created")
        return self._session

    async def close(self) -> None:
        """Close the persistent session (call during shutdown)."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.debug("Avatar: persistent HTTP session closed")

    async def check_health(self) -> bool:
        """Ping LivePortrait API. Returns True if available."""
        if not self._enabled:
            logger.info("Avatar: disabled in config")
            return False
        try:
            session = await self._get_session()
            async with session.get(
                f"{self._base_url}/health",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._available = data.get("status") in ("ok", "loading")
                    logger.info(f"Avatar: LivePortrait health = {data}")
                    return self._available
            # Non-200 status
            self._available = False
            return False
        except Exception as e:
            logger.warning(f"Avatar: LivePortrait not available ({e}) — running without avatar")
            self._available = False
            return False

    async def set_speaking(self, speaking: bool) -> None:
        """Tell LivePortrait whether Aether is currently speaking."""
        if not self._available:
            return
        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/speaking",
                json={"speaking": speaking},
                timeout=aiohttp.ClientTimeout(total=1),
            ) as resp:
                await resp.read()  # Consume response to release connection
        except Exception as e:
            logger.debug(f"Avatar: set_speaking failed (non-critical): {e}")

    async def send_audio_chunk(self, audio_b64: str) -> None:
        """Send a base64-encoded audio chunk to avatar for lip sync."""
        if not self._available:
            return
        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/audio_chunk",
                json={"audio_b64": audio_b64},
                timeout=aiohttp.ClientTimeout(total=0.5),
            ) as resp:
                await resp.read()  # Consume response to release connection
        except Exception as e:
            logger.debug(f"Avatar: send_audio_chunk failed (non-critical): {e}")

    @property
    def stream_url(self) -> str:
        return self._stream_url

    @property
    def available(self) -> bool:
        return self._available


_client: AvatarClient | None = None


def get_avatar_client() -> AvatarClient:
    """Return singleton AvatarClient instance."""
    global _client
    if _client is None:
        _client = AvatarClient()
    return _client
