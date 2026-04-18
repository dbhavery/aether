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

    Resolution order (first match wins):

    1. ``config.yaml``'s ``aether.user_installation_id`` — the steady state
       after onboarding has finalized.
    2. ``wizard_state.yaml``'s ``installation_id`` — used during onboarding,
       before ``config.yaml`` exists. Pre-persisted at the start of the
       wizard so every keyring write during the wizard uses the same UUID
       that finalize will copy into ``config.yaml``.
    3. Generate a fresh uuid4 and persist it to ``wizard_state.yaml`` so the
       very first ``set_key`` call and every subsequent call agree on a
       single UUID.

    Imports are local to avoid circular-import issues with ``config`` and to
    keep ``paths`` / ``onboarding.state`` out of this module's import graph
    when they're not needed. The ``@lru_cache`` ensures the resolution runs
    at most once per process; callers that cross the wizard→finalize
    boundary (``finalizer.finalize_wizard``) must invoke
    ``_installation_uuid.cache_clear()`` afterwards so the next read picks
    up the now-written config value.
    """
    # 1. config.yaml — post-onboarding steady state.
    try:
        from src.shared.config import get_config

        configured = get_config().aether.user_installation_id
        if configured:
            return configured
    except Exception as exc:  # config absent or invalid during onboarding
        logger.debug(f"Installation UUID not available from config: {exc!r}")

    # 2. wizard_state.yaml — mid-onboarding, pre-finalize.
    try:
        from src.onboarding.state import load_wizard_state

        state = load_wizard_state()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Could not load wizard state for installation UUID: {exc!r}")
        state = None

    if state is not None and state.installation_id:
        logger.debug("Installation UUID resolved from wizard_state.yaml")
        return state.installation_id

    # 3. No config, no wizard state — mint one and persist it to wizard_state
    #    so subsequent reads (including from this same process after a
    #    cache_clear) agree on the UUID.
    import uuid

    new_id = str(uuid.uuid4())
    try:
        from src.onboarding.state import WizardState, save_wizard_state

        seed_state = state if state is not None else WizardState()
        seed_state.installation_id = new_id
        save_wizard_state(seed_state)
        logger.info(
            f"Generated new installation UUID and persisted to wizard_state.yaml: {new_id}"
        )
    except Exception as exc:
        # Persistence failed — still return the generated UUID so this process
        # is internally consistent. The next process will mint a different
        # one, but that's better than crashing on first-run with no keyring
        # backend writes to reach.
        logger.warning(
            f"Could not persist generated installation UUID to wizard_state.yaml: "
            f"{exc!r}; using UUID in-memory only"
        )
    return new_id


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
