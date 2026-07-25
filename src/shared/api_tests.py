"""Live connectivity tests for each external API service.

Each test function returns (success: bool, message: str).
Call register_test_functions() once at startup to wire these into the
api_registry so get_service_status() can run them automatically.
"""

from __future__ import annotations

import os
import socket

import httpx
from loguru import logger

from src.shared.api_registry import get_service

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OPENCLAW_HOST = "127.0.0.1"
_OPENCLAW_PORT = 18789
_HTTP_TIMEOUT = 10.0  # seconds


# ---------------------------------------------------------------------------
# Individual test functions
# ---------------------------------------------------------------------------


def test_anthropic() -> tuple[bool, str]:
    """Check that the OpenClaw gateway is reachable (Claude routing)."""
    try:
        sock = socket.create_connection(
            (_OPENCLAW_HOST, _OPENCLAW_PORT),
            timeout=5.0,
        )
        sock.close()
        return True, f"OpenClaw gateway reachable at {_OPENCLAW_HOST}:{_OPENCLAW_PORT}"
    except OSError as exc:
        logger.error(f"Anthropic gateway test failed: {exc}")
        return False, f"Cannot reach OpenClaw gateway: {exc}"


def test_gemini() -> tuple[bool, str]:
    """Check that the OpenClaw gateway is reachable (Gemini routing)."""
    # Gemini is routed through the same gateway as Anthropic
    try:
        sock = socket.create_connection(
            (_OPENCLAW_HOST, _OPENCLAW_PORT),
            timeout=5.0,
        )
        sock.close()
        return True, f"OpenClaw gateway reachable at {_OPENCLAW_HOST}:{_OPENCLAW_PORT}"
    except OSError as exc:
        logger.error(f"Gemini gateway test failed: {exc}")
        return False, f"Cannot reach OpenClaw gateway: {exc}"


def test_elevenlabs() -> tuple[bool, str]:
    """Ping the ElevenLabs /v1/user endpoint to verify the API key."""
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        return False, "ELEVENLABS_API_KEY not set"

    try:
        response = httpx.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": api_key},
            timeout=_HTTP_TIMEOUT,
        )
        if response.status_code == 200:
            return True, "ElevenLabs API key valid"
        return False, f"ElevenLabs returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        logger.error(f"ElevenLabs test failed: {exc}")
        return False, f"HTTP error: {exc}"


def test_openai() -> tuple[bool, str]:
    """Hit the OpenAI /v1/models endpoint to verify the API key."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return False, "OPENAI_API_KEY not set"

    try:
        response = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_HTTP_TIMEOUT,
        )
        if response.status_code == 200:
            return True, "OpenAI API key valid"
        return False, f"OpenAI returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        logger.error(f"OpenAI test failed: {exc}")
        return False, f"HTTP error: {exc}"


def test_picovoice() -> tuple[bool, str]:
    """Attempt to create a Porcupine instance to validate the access key."""
    access_key = os.environ.get("PICOVOICE_ACCESS_KEY", "").strip()
    if not access_key:
        return False, "PICOVOICE_ACCESS_KEY not set"

    try:
        import pvporcupine  # type: ignore[import-untyped]

        handle = pvporcupine.create(
            access_key=access_key,
            keywords=["porcupine"],  # built-in keyword, always available
        )
        handle.delete()
        return True, "Picovoice access key valid"
    except ImportError:
        logger.error("pvporcupine package not installed")
        return False, "pvporcupine package not installed"
    except pvporcupine.PorcupineError as exc:  # type: ignore[union-attr]
        logger.error(f"Picovoice test failed: {exc}")
        return False, f"Picovoice error: {exc}"


def test_github() -> tuple[bool, str]:
    """Hit the GitHub /user endpoint to verify the personal access token."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return False, "GITHUB_TOKEN not set"

    try:
        response = httpx.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=_HTTP_TIMEOUT,
        )
        if response.status_code == 200:
            username = response.json().get("login", "unknown")
            return True, f"GitHub authenticated as {username}"
        return False, f"GitHub returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        logger.error(f"GitHub test failed: {exc}")
        return False, f"HTTP error: {exc}"


def test_tavily() -> tuple[bool, str]:
    """Hit the Tavily /search endpoint with a minimal query to verify the key."""
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return False, "TAVILY_API_KEY not set"

    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": "test",
                "max_results": 1,
            },
            timeout=_HTTP_TIMEOUT,
        )
        if response.status_code == 200:
            return True, "Tavily API key valid"
        return False, f"Tavily returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        logger.error(f"Tavily test failed: {exc}")
        return False, f"HTTP error: {exc}"


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

_TEST_MAP: dict[str, object] = {
    "anthropic": test_anthropic,
    "gemini": test_gemini,
    "elevenlabs": test_elevenlabs,
    "openai": test_openai,
    "picovoice": test_picovoice,
    "github": test_github,
    "tavily": test_tavily,
}


def register_test_functions() -> None:
    """Wire each test function onto its ServiceDefinition in the registry.

    Call this once during application startup, after the registry module has
    been imported.  Services without a test function (firebase, telegram,
    google_oauth) will simply report configured/not-configured without a
    live connectivity check.
    """
    wired = 0
    for service_name, test_fn in _TEST_MAP.items():
        svc = get_service(service_name)
        if svc is None:
            logger.warning(f"register_test_functions: service {service_name!r} not in registry")
            continue
        svc.test_fn = test_fn
        wired += 1

    logger.info(f"Wired {wired} API connectivity tests into the registry")
