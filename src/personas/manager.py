"""Runtime persona management.

`PersonaManager` owns the scanned pack dictionary and the active-persona
pointer. Switching personas publishes a `PERSONA_CHANGED` event so the voice,
avatar, and memory modules can reload their caches.

Architecture reference: ARCHITECTURE-V2.md §4.7 and §4.9.
"""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from loguru import logger

from src.personas.loader import scan_personas
from src.personas.models import PersonaPack

# NOTE: src.shared.paths does not exist yet (parallel work). We attempt the
# import and fall back to local resolution so this module remains importable
# until paths lands. Replace the fallback with direct imports once available.
try:  # pragma: no cover — import shim, behavior tested via monkeypatch
    from src.shared.paths import (  # type: ignore[attr-defined]
        get_bundled_personas_dir,
        get_personas_dir,
    )

    _USING_SHARED_PATHS = True
except ImportError:  # pragma: no cover
    _USING_SHARED_PATHS = False

    def get_bundled_personas_dir() -> Path:
        """Fallback: locate `personas/` relative to the repo root.

        Mirrors the layout described in ARCHITECTURE-V2.md §3 until
        `src.shared.paths` ships. Three parents up from this file is the
        repo root (src/personas/manager.py → src/personas/ → src/ → repo/).
        """
        return Path(__file__).resolve().parents[2] / "personas"

    def get_personas_dir() -> Path:
        """Fallback: `%APPDATA%/aether/personas/` on Windows, `~/.config/...` elsewhere."""
        if os.name == "nt":
            appdata = os.environ.get("APPDATA")
            if appdata:
                return Path(appdata) / "aether" / "personas"
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        return base / "aether" / "personas"


# NOTE: `EventType.PERSONA_CHANGED` is specified in ARCHITECTURE-V2.md §4.9 but
# not yet added to `src.shared.types.EventType`. We publish under a string
# constant so this module stays importable; when the enum value lands, swap
# `_PERSONA_CHANGED_EVENT` for the enum member.
_PERSONA_CHANGED_EVENT = "persona_changed"


class PersonaManager:
    """Holds scanned packs and the active-persona pointer.

    Obtain via `get_persona_manager()` — the module-level accessor. The class
    is not a strict singleton (each instance is independent for tests), but
    the accessor caches a process-wide instance.
    """

    def __init__(self, packs: dict[str, PersonaPack] | None = None) -> None:
        self._packs: dict[str, PersonaPack] = packs or {}
        self._active_persona_id: str | None = None
        self._lock = Lock()
        logger.debug(f"PersonaManager initialized with {len(self._packs)} pack(s)")

    # --- query API ----------------------------------------------------------

    def get(self, persona_id: str) -> PersonaPack | None:
        """Return the pack for `persona_id`, or None if unknown."""
        return self._packs.get(persona_id)

    def list_all(self) -> list[PersonaPack]:
        """Return every loaded pack, sorted by id for deterministic output."""
        return [self._packs[k] for k in sorted(self._packs)]

    def list_for_wizard(self) -> list[PersonaPack]:
        """Packs eligible for the first-run wizard.

        Current rule: every loaded pack is eligible. Reference packs are
        filtered at scan time (underscore-prefixed folder names), so anything
        reaching the manager is user-facing. If per-pack wizard flags are
        added to the schema later, gate them here.
        """
        return self.list_all()

    @property
    def active_persona_id(self) -> str | None:
        return self._active_persona_id

    @property
    def active_persona(self) -> PersonaPack | None:
        """Currently active pack, or None if `set_active` has not been called."""
        if self._active_persona_id is None:
            return None
        return self._packs.get(self._active_persona_id)

    # --- mutation API -------------------------------------------------------

    def set_active(self, persona_id: str) -> None:
        """Switch the active persona and publish PERSONA_CHANGED.

        Raises:
            KeyError: `persona_id` is not a loaded pack.
        """
        if persona_id not in self._packs:
            raise KeyError(
                f"persona '{persona_id}' is not loaded — available: {sorted(self._packs)}"
            )

        with self._lock:
            previous_id = self._active_persona_id
            if previous_id == persona_id:
                logger.debug(f"PersonaManager.set_active: {persona_id} already active — no-op")
                return
            self._active_persona_id = persona_id

        logger.info(f"persona: active changed {previous_id!r} -> {persona_id!r}")
        self._emit_persona_changed(previous_id=previous_id, new_id=persona_id)

    def reload(self) -> None:
        """Re-scan both persona directories and replace the pack dictionary.

        Called by the user's "refresh personas" action. The active persona is
        preserved if it still exists after reload; otherwise it is cleared and
        PERSONA_CHANGED is published with `previous_id` set.
        """
        bundled = get_bundled_personas_dir()
        user = get_personas_dir()
        logger.info(f"persona: reloading from bundled={bundled} user={user}")

        new_packs = scan_personas(bundled, user)

        with self._lock:
            self._packs = new_packs
            previous_id = self._active_persona_id
            if previous_id is not None and previous_id not in new_packs:
                self._active_persona_id = None
                logger.warning(
                    f"persona: active '{previous_id}' disappeared after reload — cleared"
                )
                active_cleared = True
            else:
                active_cleared = False

        if active_cleared:
            self._emit_persona_changed(previous_id=previous_id, new_id=None)

    # --- internals ----------------------------------------------------------

    def _emit_persona_changed(self, *, previous_id: str | None, new_id: str | None) -> None:
        """Publish the PERSONA_CHANGED event on the process-wide EventBus.

        Synchronous contexts (tests, module init) are supported by using
        `asyncio.get_event_loop().create_task` only when a loop is running.
        When no loop is available we log and skip the publish — the caller
        can re-emit once the loop is up.
        """
        import asyncio

        try:
            from src.core.events import event_bus
            from src.shared.types import AetherEvent, EventType
        except ImportError as exc:  # pragma: no cover
            logger.warning(f"persona: EventBus unavailable ({exc}); skipping publish")
            return

        # Prefer the enum member if it has been added; fall back to a string.
        event_type = getattr(EventType, "PERSONA_CHANGED", _PERSONA_CHANGED_EVENT)
        event = AetherEvent(
            type=event_type,  # type: ignore[arg-type]  # string fallback until enum lands
            data={"persona_id": new_id, "previous_id": previous_id},
            source_module="src.personas.manager",
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — common in tests and CLI. Record at debug so
            # it's visible but not alarming, and let the caller drive the publish.
            logger.debug(
                f"persona: no running loop; PERSONA_CHANGED for {new_id!r} not published"
            )
            return

        loop.create_task(event_bus.publish(event))


# ---------------------------------------------------------------------------
# Module-level accessor.
# ---------------------------------------------------------------------------

_instance: PersonaManager | None = None
_instance_lock = Lock()


def get_persona_manager() -> PersonaManager:
    """Return the process-wide PersonaManager, constructing on first call.

    On first call it runs a disk scan via `scan_personas`. Subsequent calls
    return the cached instance. Use `PersonaManager.reload()` to re-scan.
    """
    global _instance
    with _instance_lock:
        if _instance is None:
            bundled = get_bundled_personas_dir()
            user = get_personas_dir()
            logger.debug(
                f"PersonaManager bootstrap: bundled={bundled} user={user} "
                f"(shared_paths={_USING_SHARED_PATHS})"
            )
            packs = scan_personas(bundled, user)
            _instance = PersonaManager(packs=packs)
        return _instance


def _reset_for_tests() -> None:
    """Clear the cached singleton. Tests only — not part of the public API."""
    global _instance
    with _instance_lock:
        _instance = None


__all__ = ["PersonaManager", "get_persona_manager"]
