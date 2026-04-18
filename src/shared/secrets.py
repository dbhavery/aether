"""OS-keyring-backed secrets storage for LLM / TTS provider API keys.

Aether never persists API keys in plaintext. The primary store is the OS
keyring (Windows Credential Manager, macOS Keychain, Secret Service on
Linux) accessed via the ``keyring`` Python library. Keys are stored under
service name ``aether.<provider>`` with the username being the per-install
UUID read from ``config.yaml``.

Env-var fallback
----------------
If no key exists in the keyring for a provider, ``get_key()`` falls back to
the conventional environment variable (``{PROVIDER_UPPER}_API_KEY``) so
developers can export keys in a shell without writing them to disk. The
fallback is a read-only convenience — ``set_key`` / ``delete_key`` always
operate on the keyring.

Keyring unavailability
----------------------
Some environments (headless CI without ``dbus``, sandboxed containers) have
no keyring backend. In that case ``get_key`` returns ``None`` (or the env
fallback), ``list_providers`` returns ``[]``, and ``set_key`` / ``delete_key``
raise ``RuntimeError`` so the caller can surface a clear error to the user.
"""

from __future__ import annotations

import os
from functools import lru_cache

import keyring
from keyring.errors import KeyringError, NoKeyringError
from loguru import logger

_SERVICE_PREFIX = "aether."
_PROVIDER_INDEX_USERNAME = "__provider_index__"
_PROVIDER_INDEX_SERVICE = "aether._index"


def _service_name(provider: str) -> str:
    """Return the canonical keyring service name for ``provider``."""
    return f"{_SERVICE_PREFIX}{provider}"


def _env_var_name(provider: str) -> str:
    """Return the env-var name used as a fallback when the keyring has no entry."""
    return f"{provider.upper()}_API_KEY"


@lru_cache(maxsize=1)
def _installation_uuid() -> str:
    """Return the per-install UUID used as the keyring username.

    Imports locally to avoid a circular import with ``config``.
    """
    try:
        from src.shared.config import get_config

        return get_config().aether.user_installation_id
    except Exception as exc:  # pragma: no cover - config errors handled elsewhere
        logger.warning(f"Could not read installation UUID from config: {exc!r}; using 'default'")
        return "default"


def _keyring_available() -> bool:
    """Return True iff a usable keyring backend is installed."""
    try:
        keyring.get_keyring()
        return True
    except NoKeyringError:
        logger.warning("No keyring backend available on this system")
        return False
    except KeyringError as exc:
        logger.warning(f"Keyring backend reported error: {exc!r}")
        return False


def _read_provider_index() -> set[str]:
    """Return the set of providers tracked in the keyring's index entry."""
    if not _keyring_available():
        return set()
    try:
        raw = keyring.get_password(_PROVIDER_INDEX_SERVICE, _PROVIDER_INDEX_USERNAME)
    except KeyringError as exc:
        logger.warning(f"Failed to read provider index from keyring: {exc!r}")
        return set()
    if not raw:
        return set()
    return {p for p in raw.split(",") if p}


def _write_provider_index(providers: set[str]) -> None:
    """Persist the provider index (sorted, comma-joined) to the keyring."""
    if not _keyring_available():
        raise RuntimeError("Cannot write provider index: no keyring backend available")
    payload = ",".join(sorted(providers))
    try:
        keyring.set_password(_PROVIDER_INDEX_SERVICE, _PROVIDER_INDEX_USERNAME, payload)
    except KeyringError as exc:
        raise RuntimeError(f"Failed to persist provider index: {exc!r}") from exc


def get_key(provider: str) -> str | None:
    """Return the API key for ``provider`` from keyring, or env var, or None."""
    if not provider:
        raise ValueError("provider must be a non-empty string")

    if _keyring_available():
        try:
            value = keyring.get_password(_service_name(provider), _installation_uuid())
            if value:
                return value
        except KeyringError as exc:
            logger.warning(f"Keyring read failed for provider={provider!r}: {exc!r}")

    env_value = os.environ.get(_env_var_name(provider), "").strip()
    if env_value:
        logger.debug(f"Using env-var fallback for provider={provider!r}")
        return env_value

    return None


def set_key(provider: str, key: str) -> None:
    """Write ``key`` for ``provider`` to the OS keyring."""
    if not provider:
        raise ValueError("provider must be a non-empty string")
    if not key:
        raise ValueError("key must be a non-empty string")

    if not _keyring_available():
        raise RuntimeError(
            "Cannot store API key: no OS keyring backend is available on this system"
        )

    try:
        keyring.set_password(_service_name(provider), _installation_uuid(), key)
    except KeyringError as exc:
        raise RuntimeError(f"Failed to write key for provider={provider!r}: {exc!r}") from exc

    providers = _read_provider_index()
    providers.add(provider)
    _write_provider_index(providers)
    logger.info(f"Stored API key for provider={provider!r} in OS keyring")


def delete_key(provider: str) -> None:
    """Remove the stored key for ``provider`` from the OS keyring (no-op if absent)."""
    if not provider:
        raise ValueError("provider must be a non-empty string")

    if not _keyring_available():
        raise RuntimeError(
            "Cannot delete API key: no OS keyring backend is available on this system"
        )

    try:
        keyring.delete_password(_service_name(provider), _installation_uuid())
        logger.info(f"Deleted API key for provider={provider!r} from OS keyring")
    except keyring.errors.PasswordDeleteError:
        logger.debug(f"delete_key: no entry for provider={provider!r}")
    except KeyringError as exc:
        raise RuntimeError(f"Failed to delete key for provider={provider!r}: {exc!r}") from exc

    providers = _read_provider_index()
    if provider in providers:
        providers.discard(provider)
        _write_provider_index(providers)


def list_providers() -> list[str]:
    """Return providers that currently have a key stored in the keyring."""
    return sorted(_read_provider_index())
