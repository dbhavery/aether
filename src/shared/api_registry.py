"""Central registry of all external API integrations.

Every third-party service Aether talks to is declared here once.
Other modules import from this registry instead of hardcoding service details.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from loguru import logger


class AuthMethod(StrEnum):
    """How we authenticate with the external service."""

    API_KEY = "api_key"
    GATEWAY = "gateway"
    OAUTH = "oauth"


class ServiceCategory(StrEnum):
    """Logical grouping for the settings UI."""

    LLM = "LLM"
    VOICE = "Voice"
    NOTIFICATIONS = "Notifications"
    TOOLS = "Tools"


@dataclass
class ServiceDefinition:
    """A single external API that Aether depends on."""

    name: str
    display_name: str
    auth_method: AuthMethod
    env_var: str
    category: ServiceCategory
    required: bool = False
    docs_url: str = ""
    description: str = ""
    test_fn: Callable[[], tuple[bool, str]] | None = None


@dataclass
class ServiceStatus:
    """Runtime status snapshot for one service."""

    name: str
    configured: bool
    key_present: bool
    connected: bool | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Registry singleton
# ---------------------------------------------------------------------------

_SERVICES: dict[str, ServiceDefinition] = {}


def _register(svc: ServiceDefinition) -> None:
    """Add a service to the global registry (called at module load time)."""
    if svc.name in _SERVICES:
        logger.warning(f"Duplicate service registration: {svc.name}")
    _SERVICES[svc.name] = svc


# ---------------------------------------------------------------------------
# Built-in service definitions
# ---------------------------------------------------------------------------

_register(
    ServiceDefinition(
        name="anthropic",
        display_name="Claude (Anthropic)",
        auth_method=AuthMethod.GATEWAY,
        env_var="ANTHROPIC_API_KEY",
        category=ServiceCategory.LLM,
        required=True,
        docs_url="https://docs.anthropic.com/",
        description="Primary LLM — routed through OpenClaw gateway.",
    )
)

_register(
    ServiceDefinition(
        name="gemini",
        display_name="Google Gemini",
        auth_method=AuthMethod.GATEWAY,
        env_var="GOOGLE_API_KEY",
        category=ServiceCategory.LLM,
        required=False,
        docs_url="https://ai.google.dev/docs",
        description="Secondary LLM for real-time tasks and grounding.",
    )
)

_register(
    ServiceDefinition(
        name="openai",
        display_name="OpenAI",
        auth_method=AuthMethod.API_KEY,
        env_var="OPENAI_API_KEY",
        category=ServiceCategory.LLM,
        required=False,
        docs_url="https://platform.openai.com/docs",
        description="Optional LLM fallback.",
    )
)

_register(
    ServiceDefinition(
        name="elevenlabs",
        display_name="ElevenLabs",
        auth_method=AuthMethod.API_KEY,
        env_var="ELEVENLABS_API_KEY",
        category=ServiceCategory.VOICE,
        required=False,
        docs_url="https://elevenlabs.io/docs",
        description="Cloud TTS fallback and STT (Scribe v2).",
    )
)

_register(
    ServiceDefinition(
        name="picovoice",
        display_name="Picovoice (Porcupine)",
        auth_method=AuthMethod.API_KEY,
        env_var="PICOVOICE_ACCESS_KEY",
        category=ServiceCategory.VOICE,
        required=False,
        docs_url="https://picovoice.ai/docs/porcupine/",
        description="Wake word detection engine.",
    )
)

_register(
    ServiceDefinition(
        name="firebase",
        display_name="Firebase (FCM)",
        auth_method=AuthMethod.API_KEY,
        env_var="FIREBASE_SERVICE_ACCOUNT_PATH",
        category=ServiceCategory.NOTIFICATIONS,
        required=False,
        docs_url="https://firebase.google.com/docs/cloud-messaging",
        description="Android push notifications via FCM.",
    )
)

_register(
    ServiceDefinition(
        name="telegram",
        display_name="Telegram Bot",
        auth_method=AuthMethod.API_KEY,
        env_var="TELEGRAM_BOT_TOKEN",
        category=ServiceCategory.NOTIFICATIONS,
        required=False,
        docs_url="https://core.telegram.org/bots/api",
        description="Telegram bot for remote messaging.",
    )
)

_register(
    ServiceDefinition(
        name="telegram_chat",
        display_name="Telegram Chat ID",
        auth_method=AuthMethod.API_KEY,
        env_var="TELEGRAM_CHAT_ID",
        category=ServiceCategory.NOTIFICATIONS,
        required=False,
        docs_url="https://t.me/userinfobot",
        description="Your Telegram chat ID for crash alerts. Get it from @userinfobot.",
    )
)

_register(
    ServiceDefinition(
        name="google_oauth",
        display_name="Google OAuth",
        auth_method=AuthMethod.API_KEY,
        env_var="GOOGLE_OAUTH_CLIENT_PATH",
        category=ServiceCategory.TOOLS,
        required=False,
        docs_url="https://developers.google.com/identity/protocols/oauth2",
        description="OAuth credentials for Google Calendar, Gmail, etc.",
    )
)

_register(
    ServiceDefinition(
        name="github",
        display_name="GitHub",
        auth_method=AuthMethod.API_KEY,
        env_var="GITHUB_TOKEN",
        category=ServiceCategory.TOOLS,
        required=False,
        docs_url="https://docs.github.com/en/rest",
        description="GitHub API for repo operations and issue tracking.",
    )
)

_register(
    ServiceDefinition(
        name="tavily",
        display_name="Tavily Search",
        auth_method=AuthMethod.API_KEY,
        env_var="TAVILY_API_KEY",
        category=ServiceCategory.TOOLS,
        required=False,
        docs_url="https://docs.tavily.com/",
        description="Web search API for research agent.",
    )
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_service(name: str) -> ServiceDefinition | None:
    """Return a service definition by name, or None if not registered."""
    svc = _SERVICES.get(name)
    if svc is None:
        logger.warning(f"Requested unknown service: {name}")
    return svc


def get_services_by_category(category: ServiceCategory) -> list[ServiceDefinition]:
    """Return all services belonging to a given category."""
    return [svc for svc in _SERVICES.values() if svc.category == category]


def get_service_status(name: str) -> ServiceStatus | None:
    """Check whether a single service is configured and optionally test it.

    Returns None if the service is not registered.
    """
    svc = get_service(name)
    if svc is None:
        return None

    key_present = bool(os.environ.get(svc.env_var, "").strip())

    connected: bool | None = None
    message = ""

    if svc.test_fn is not None and key_present:
        try:
            connected, message = svc.test_fn()
        except Exception as exc:
            logger.error(f"Test function for {name} raised unexpectedly: {exc}")
            connected = False
            message = f"Test error: {exc}"

    return ServiceStatus(
        name=svc.name,
        configured=key_present,
        key_present=key_present,
        connected=connected,
        message=message,
    )


def get_all_statuses() -> list[ServiceStatus]:
    """Return status snapshots for every registered service."""
    statuses: list[ServiceStatus] = []
    for name in _SERVICES:
        status = get_service_status(name)
        if status is not None:
            statuses.append(status)
    return statuses


def all_services() -> list[ServiceDefinition]:
    """Return every registered service definition."""
    return list(_SERVICES.values())
