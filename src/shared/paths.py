"""Centralized filesystem path resolution for Aether.

Aether is installable anywhere on a user's machine (pip install, Inno Setup
installer, `python -m src.main` from a source checkout). We cannot assume the
current working directory, the location of `src/`, or that the user has write
access to the install directory. Every path the backend touches therefore
resolves through this module.

Dual strategy
-------------
1. **User-generated state** (config, SQLite, ChromaDB, logs, downloaded models,
   user-created persona overrides) lives under the per-OS user data directory
   as reported by ``platformdirs``. On Windows this is
   ``%APPDATA%/aether/``; on macOS ``~/Library/Application Support/aether``;
   on Linux ``~/.local/share/aether``. This directory is always writable,
   survives upgrades, and is not scanned by packagers.

2. **Bundled read-only assets** (persona packs shipped with the app, schemas,
   default configs) live inside the repo/install tree and are resolved
   relative to this file by walking up to the repo root. They must never be
   written to at runtime — user overrides go in (1).

Every getter creates the directory it returns if it does not already exist
(except for paths that represent files, and for the read-only bundled
personas directory). Creation is idempotent and race-safe via
``mkdir(parents=True, exist_ok=True)``.

Overrides
---------
``AETHER_DATA_DIR`` env var, when set and non-empty, replaces the default
user data directory. Useful for tests, portable installs, and multi-profile
development. The directory is created if missing. All data-dir-derived paths
(chroma, models, personas, logs, conversations.db) inherit the override.
"""

from __future__ import annotations

import os
from pathlib import Path

import platformdirs

_APP_NAME = "aether"
_APP_AUTHOR = "aether"
_DATA_DIR_ENV_VAR = "AETHER_DATA_DIR"


def _ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if missing; return it unchanged."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir() -> Path:
    """Return the writable user data directory (creates it if missing).

    Overridable via the ``AETHER_DATA_DIR`` environment variable.
    """
    override = os.environ.get(_DATA_DIR_ENV_VAR, "").strip()
    if override:
        return _ensure_dir(Path(override).expanduser().resolve())
    return _ensure_dir(Path(platformdirs.user_data_dir(_APP_NAME, _APP_AUTHOR)))


def get_config_dir() -> Path:
    """Return the writable user config directory (creates it if missing)."""
    return _ensure_dir(Path(platformdirs.user_config_dir(_APP_NAME, _APP_AUTHOR)))


def get_cache_dir() -> Path:
    """Return the writable user cache directory (creates it if missing)."""
    return _ensure_dir(Path(platformdirs.user_cache_dir(_APP_NAME, _APP_AUTHOR)))


def get_logs_dir() -> Path:
    """Return the logs directory under the data dir (creates it if missing)."""
    return _ensure_dir(get_data_dir() / "logs")


def get_chroma_dir() -> Path:
    """Return the ChromaDB root directory (creates it if missing)."""
    return _ensure_dir(get_data_dir() / "chroma")


def get_models_dir() -> Path:
    """Return the downloaded-models directory (creates it if missing)."""
    return _ensure_dir(get_data_dir() / "models")


def get_personas_dir() -> Path:
    """Return the user-created/override personas directory (creates it if missing)."""
    return _ensure_dir(get_data_dir() / "personas")


def get_bundled_personas_dir() -> Path:
    """Return the repo-bundled persona packs directory (read-only).

    Resolves by walking up from this file to the repo root; the directory
    must exist in the install tree. Does NOT create it — a missing directory
    here indicates a broken install and should fail loudly at the call site.
    """
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "personas"


def get_config_path() -> Path:
    """Return the full path to the user's ``config.yaml`` file."""
    return get_config_dir() / "config.yaml"


def get_wizard_state_path() -> Path:
    """Return the full path to the onboarding wizard state file."""
    return get_config_dir() / "wizard_state.yaml"


def get_conversations_db_path() -> Path:
    """Return the full path to the SQLite conversations database."""
    return get_data_dir() / "conversations.db"
