"""Onboarding wizard state machine and durable persistence.

The wizard is a linear 8-step flow (WELCOME → HANDOFF); every validated step's
submission is persisted to ``%APPDATA%/aether/wizard_state.yaml`` so the user
can quit and resume later without re-entering choices or API keys.

Persistence uses ruamel.yaml for comment-preserving round-trip. Writes are
atomic: we write to ``<path>.tmp`` and ``os.replace`` onto the final path so a
crash mid-write never corrupts the state file.

Secrets policy: this file holds *no* API keys. Keys are handed to the keyring
as soon as Screen 5 validates and are never serialised into state.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from ruamel.yaml import YAML

# NOTE: get_wizard_state_path lives in src.shared.paths (already shipped).
from src.shared.paths import get_wizard_state_path


class WizardStep(StrEnum):
    """Canonical step identifiers — the values double as URL-safe slugs."""

    WELCOME = "1-welcome"
    AVATAR = "2-avatar"
    PERSONALITY = "3-personality"
    NAME = "4-name"
    LLM = "5-llm"
    VOICE = "6-voice"
    TERMS = "7-terms"
    HANDOFF = "8-handoff"


# Ordered sequence used to derive the "next" step from the current one.
_STEP_ORDER: tuple[WizardStep, ...] = (
    WizardStep.WELCOME,
    WizardStep.AVATAR,
    WizardStep.PERSONALITY,
    WizardStep.NAME,
    WizardStep.LLM,
    WizardStep.VOICE,
    WizardStep.TERMS,
    WizardStep.HANDOFF,
)


def next_step(current: WizardStep) -> WizardStep | None:
    """Return the step that follows ``current``, or None if ``current`` is terminal."""
    try:
        idx = _STEP_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(_STEP_ORDER):
        return None
    return _STEP_ORDER[idx + 1]


class TelemetryPrefs(BaseModel):
    """Opt-in telemetry switches collected on the Terms screen."""

    model_config = ConfigDict(extra="forbid")

    crash_reports: bool = False
    usage_counters: bool = False


class WizardState(BaseModel):
    """Durable snapshot of the wizard's progress.

    Every field is optional until its owning step is validated, then set and
    never cleared (except via ``clear_wizard_state`` at HANDOFF completion).
    """

    model_config = ConfigDict(extra="forbid")

    # Timing
    started_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())

    # Per-install UUID — populated at the first ``save_wizard_state`` call so
    # keyring writes during the wizard and keyring reads after finalize agree
    # on a single username. Finalize copies this into
    # ``config.yaml``'s ``aether.user_installation_id``.
    installation_id: str | None = None

    # Progress
    current_step: WizardStep = WizardStep.WELCOME
    completed_steps: list[WizardStep] = Field(default_factory=list)

    # Screen 2 — avatar (visual)
    selected_avatar_id: str | None = None

    # Screen 3 — personality (behavioral archetype)
    selected_archetype: str | None = None

    # Screen 4 — display name
    display_name: str | None = None

    # Screen 5 — LLM
    llm_provider: str | None = None
    llm_tier_map: dict[str, str] | None = None
    llm_model_overrides: dict[str, str] | None = None

    # Screen 6 — voice
    voice_mode: str | None = None  # "local" | "elevenlabs" | "off"
    voice_settings: dict[str, Any] = Field(default_factory=dict)

    # Screen 7 — terms
    accepted_terms_at: datetime | None = None
    telemetry: TelemetryPrefs = Field(default_factory=TelemetryPrefs)

    def mark_step_complete(self, step: WizardStep) -> None:
        """Record ``step`` as complete and advance ``current_step`` if applicable."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        following = next_step(step)
        if following is not None:
            self.current_step = following
        self.last_updated_at = datetime.now().astimezone()


def _yaml() -> YAML:
    """Return a configured ruamel.yaml instance (round-trip, 2-space indent)."""
    y = YAML(typ="rt")
    y.indent(mapping=2, sequence=4, offset=2)
    y.default_flow_style = False
    return y


def _serialise(state: WizardState) -> str:
    """Render ``state`` to a YAML string via ruamel.yaml."""
    # Pydantic -> plain dict with JSON-safe primitives (datetimes as ISO strings,
    # enums as their .value). ruamel.yaml then pretty-prints that dict.
    plain: dict[str, Any] = state.model_dump(mode="json")
    buf = StringIO()
    _yaml().dump(plain, buf)
    return buf.getvalue()


def load_wizard_state() -> WizardState | None:
    """Return the persisted ``WizardState``, or None if no state file exists.

    A corrupt state file is logged and treated as absent — the caller can
    choose whether to restart the wizard or surface an error.
    """
    path = get_wizard_state_path()
    if not path.exists():
        logger.debug(f"Wizard state absent at {path}")
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error(f"Failed to read wizard state at {path}: {exc!r}")
        return None
    try:
        data = _yaml().load(raw)
    except Exception as exc:  # ruamel raises a variety of subclasses
        logger.error(f"Failed to parse wizard state at {path}: {exc!r}")
        return None
    if not isinstance(data, dict):
        logger.error(f"Wizard state at {path} is not a mapping (got {type(data).__name__})")
        return None
    try:
        return WizardState.model_validate(dict(data))
    except Exception as exc:
        logger.error(f"Wizard state at {path} failed schema validation: {exc!r}")
        return None


def save_wizard_state(state: WizardState) -> None:
    """Persist ``state`` atomically to disk.

    Writes to ``<path>.tmp`` and then ``os.replace`` onto the final path so an
    interrupted write cannot corrupt an existing state file.

    If ``state.installation_id`` is unset, generates a uuid4 and stamps it
    before the write so every subsequent save sees the same value. This is
    the canonical point where the wizard-scoped UUID is materialised — the
    secrets module reads it back to keep keyring writes/reads consistent
    across the wizard→finalize boundary.
    """
    if state.installation_id is None:
        state.installation_id = str(uuid.uuid4())
        logger.debug(f"Assigned wizard installation_id={state.installation_id}")
    state.last_updated_at = datetime.now().astimezone()
    path = get_wizard_state_path()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    payload = _serialise(state)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError as exc:
        # Best-effort cleanup of the temp file so stale .tmp doesn't accumulate.
        _silently_remove(tmp_path)
        raise RuntimeError(f"Failed to write wizard state to {path}: {exc!r}") from exc
    logger.debug(f"Wizard state saved (step={state.current_step}, path={path})")


def clear_wizard_state() -> None:
    """Delete the wizard state file. No-op if the file is already absent."""
    path = get_wizard_state_path()
    try:
        path.unlink()
        logger.info(f"Wizard state cleared ({path})")
    except FileNotFoundError:
        logger.debug(f"Wizard state already absent ({path})")
    except OSError as exc:
        raise RuntimeError(f"Failed to clear wizard state at {path}: {exc!r}") from exc


def _silently_remove(path: Path) -> None:
    """Delete ``path`` swallowing FileNotFoundError; log other OS errors."""
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning(f"Failed to remove temp wizard-state file {path}: {exc!r}")
