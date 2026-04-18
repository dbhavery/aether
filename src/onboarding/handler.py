"""EventBus handler bridging WebSocket wizard events to the state machine.

The frontend fires one ``WIZARD_STEP_SUBMIT`` per user confirmation. This
module validates the submission, persists state, and replies with exactly one
``WIZARD_STEP_RESULT``. On HANDOFF it additionally calls ``finalize_wizard``
(which writes ``config.yaml`` and emits ``ONBOARDING_COMPLETE``).

Event payload contract
----------------------
IN — ``WIZARD_STEP_SUBMIT.data``::

    {
        "step": "2-avatar",            # WizardStep value
        "payload": { ... step-specific fields ... },
    }

OUT — ``WIZARD_STEP_RESULT.data``::

    {
        "step": "2-avatar",
        "ok": true,
        "next_step": "3-personality",  # None on HANDOFF success
        "error": None,                 # set on failure; ok will be False
    }
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from src.core.events import event_bus
from src.onboarding.finalizer import FinalizeError, finalize_wizard
from src.onboarding.state import (
    TelemetryPrefs,
    WizardState,
    WizardStep,
    load_wizard_state,
    next_step,
    save_wizard_state,
)
from src.onboarding.validators import (
    validate_archetype,
    validate_avatar,
    validate_display_name,
    validate_llm_provider,
    validate_terms_acceptance,
    validate_voice_mode,
)
from src.shared.secrets import set_key
from src.shared.types import AetherEvent, EventType

_SOURCE_MODULE = "onboarding.handler"


def register_wizard_handlers() -> None:
    """Subscribe the wizard handler to the EventBus. Idempotent."""
    event_bus.subscribe(EventType.WIZARD_STEP_SUBMIT, _handle_wizard_step_submit)
    logger.info("Onboarding wizard handlers registered")


async def _handle_wizard_step_submit(event: AetherEvent) -> None:
    """Entrypoint — dispatch by step, validate, persist, reply."""
    step_raw = event.data.get("step")
    payload = event.data.get("payload") or {}
    if not isinstance(payload, dict):
        await _reply(step_raw, ok=False, error="Wizard payload must be an object.")
        return

    step = _coerce_step(step_raw)
    if step is None:
        await _reply(step_raw, ok=False, error=f"Unknown wizard step '{step_raw}'.")
        return

    state = load_wizard_state() or WizardState()

    try:
        ok, error = await _dispatch(step, payload, state)
    except Exception as exc:  # Defensive — no handler should raise, but don't crash the bus.
        logger.exception(f"Unhandled error in wizard step {step}: {exc!r}")
        await _reply(step.value, ok=False, error="Internal error during validation.")
        return

    if not ok:
        await _reply(step.value, ok=False, error=error)
        return

    state.mark_step_complete(step)

    # HANDOFF finalises everything; it has its own success event on top of
    # WIZARD_STEP_RESULT so the frontend can transition to chat mode.
    if step is WizardStep.HANDOFF:
        try:
            await finalize_wizard(state)
        except FinalizeError as exc:
            logger.error(f"Finalization failed: {exc!r}")
            await _reply(step.value, ok=False, error=str(exc))
            return
        await _reply(step.value, ok=True, next_step=None)
        await event_bus.publish(
            AetherEvent(
                type=EventType.ONBOARDING_COMPLETE,
                data={
                    "completed_at": datetime.now().astimezone().isoformat(),
                    "persona_id": state.selected_avatar_id,
                    "archetype": state.selected_archetype,
                    "display_name": state.display_name,
                },
                source_module=_SOURCE_MODULE,
            )
        )
        return

    try:
        save_wizard_state(state)
    except RuntimeError as exc:
        logger.error(f"Failed to persist wizard state: {exc!r}")
        await _reply(step.value, ok=False, error="Couldn't save wizard progress.")
        return

    await _reply(step.value, ok=True, next_step=_as_value(next_step(step)))


# ---------------------------------------------------------------------------
# Step dispatch — each branch validates and mutates ``state`` in place.
# ---------------------------------------------------------------------------


async def _dispatch(
    step: WizardStep, payload: dict[str, Any], state: WizardState
) -> tuple[bool, str | None]:
    """Route ``step`` to the matching validator and fold results into ``state``."""
    if step is WizardStep.WELCOME:
        # No user input; just stamp start time if not already set.
        if state.started_at is None:  # pragma: no cover — default_factory always sets it
            state.started_at = datetime.now().astimezone()
        return True, None

    if step is WizardStep.AVATAR:
        avatar_id = payload.get("avatar_id", "")
        ok, error = validate_avatar(str(avatar_id))
        if ok:
            state.selected_avatar_id = str(avatar_id).strip().lower()
        return ok, error

    if step is WizardStep.PERSONALITY:
        archetype = payload.get("archetype", "")
        ok, error = validate_archetype(str(archetype))
        if ok:
            state.selected_archetype = str(archetype).strip()
        return ok, error

    if step is WizardStep.NAME:
        name = payload.get("display_name", "")
        ok, error = validate_display_name(str(name) if name is not None else "")
        if ok:
            state.display_name = str(name).strip()
        return ok, error

    if step is WizardStep.LLM:
        provider = str(payload.get("provider", ""))
        key = payload.get("key")
        model_overrides = payload.get("model_overrides") or {}
        if not isinstance(model_overrides, dict):
            return False, "model_overrides must be an object."
        ok, error = await validate_llm_provider(
            provider, key if isinstance(key, str) else None, model_overrides
        )
        if not ok:
            return ok, error
        provider_lc = provider.strip().lower()
        state.llm_provider = provider_lc
        state.llm_tier_map = (
            payload.get("tier_map") if isinstance(payload.get("tier_map"), dict) else None
        )
        state.llm_model_overrides = model_overrides or None
        # Per LLM-PROVIDERS.md §6 and ONBOARDING-SPEC.md §3, API keys go to
        # the OS keyring the moment a provider validates — never to disk in
        # plaintext, never to wizard_state.yaml. The key is gone from memory
        # after this block returns.
        if isinstance(key, str) and key.strip() and provider_lc not in {"ollama", "aether_guest"}:
            try:
                set_key(provider_lc, key.strip())
            except (RuntimeError, ValueError) as exc:
                logger.error(f"Keyring write failed for provider={provider_lc!r}: {exc!r}")
                return False, "Could not securely store your API key. Check system keyring access."
        return True, None

    if step is WizardStep.VOICE:
        mode = str(payload.get("mode", ""))
        settings = payload.get("settings") or {}
        if not isinstance(settings, dict):
            return False, "settings must be an object."
        ok, error = await validate_voice_mode(mode, settings)
        if not ok:
            return ok, error
        mode_lc = mode.strip().lower()
        state.voice_mode = mode_lc
        # Strip the key out of settings before it hits disk.
        sanitised = {k: v for k, v in settings.items() if k != "api_key"}
        state.voice_settings = sanitised
        if mode_lc == "elevenlabs":
            el_key = settings.get("api_key")
            if isinstance(el_key, str) and el_key.strip():
                try:
                    set_key("elevenlabs", el_key.strip())
                except (RuntimeError, ValueError) as exc:
                    logger.error(f"Keyring write failed for provider='elevenlabs': {exc!r}")
                    return False, "Could not securely store your ElevenLabs key."
        return True, None

    if step is WizardStep.TERMS:
        accepted = bool(payload.get("accepted", False))
        crash_reports = bool(payload.get("crash_reports", False))
        usage_counters = bool(payload.get("usage_counters", False))
        ok, error = validate_terms_acceptance(accepted, crash_reports, usage_counters)
        if ok:
            state.accepted_terms_at = datetime.now().astimezone()
            state.telemetry = TelemetryPrefs(
                crash_reports=crash_reports, usage_counters=usage_counters
            )
        return ok, error

    if step is WizardStep.HANDOFF:
        # Validation for HANDOFF is "every prior step completed".
        missing = _missing_prerequisites(state)
        if missing:
            return False, f"Cannot finalize — missing: {', '.join(m.value for m in missing)}."
        return True, None

    return False, f"Unsupported wizard step '{step.value}'."  # pragma: no cover


def _missing_prerequisites(state: WizardState) -> list[WizardStep]:
    """Return steps whose required outputs are missing before HANDOFF."""
    missing: list[WizardStep] = []
    if state.selected_avatar_id is None:
        missing.append(WizardStep.AVATAR)
    if state.selected_archetype is None:
        missing.append(WizardStep.PERSONALITY)
    if not state.display_name:
        missing.append(WizardStep.NAME)
    if not state.llm_provider:
        missing.append(WizardStep.LLM)
    if not state.voice_mode:
        missing.append(WizardStep.VOICE)
    if state.accepted_terms_at is None:
        missing.append(WizardStep.TERMS)
    return missing


# ---------------------------------------------------------------------------
# Plumbing.
# ---------------------------------------------------------------------------


def _coerce_step(raw: Any) -> WizardStep | None:
    """Parse a raw event value into a ``WizardStep``, or None if invalid."""
    if isinstance(raw, WizardStep):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return WizardStep(raw)
    except ValueError:
        return None


def _as_value(step: WizardStep | None) -> str | None:
    return step.value if step is not None else None


async def _reply(
    step: Any,
    *,
    ok: bool,
    next_step: str | None = None,  # noqa: ARG001 — name matches spec
    error: str | None = None,
) -> None:
    """Publish a ``WIZARD_STEP_RESULT`` back onto the bus."""
    data: dict[str, Any] = {
        "step": step.value if isinstance(step, WizardStep) else step,
        "ok": ok,
        "next_step": next_step,
        "error": error,
    }
    await event_bus.publish(
        AetherEvent(type=EventType.WIZARD_STEP_RESULT, data=data, source_module=_SOURCE_MODULE)
    )
