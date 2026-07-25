"""Onboarding wizard — first-run state machine, validators, and config writer.

The wizard is driven by the Next.js frontend over WebSocket. Each step's
submission fires a ``WIZARD_STEP_SUBMIT`` event; the backend validates the
submission (making real provider test calls where applicable), persists the
validated state to ``wizard_state.yaml`` atomically, and emits a
``WIZARD_STEP_RESULT`` event.

API keys are written to the OS keyring the moment their validation step
passes (never to the wizard state file). On the final HANDOFF step the
wizard runs ``finalize_wizard`` which:

1. Atomically writes ``config.yaml`` with ``onboarding.complete: true``.
2. Creates the active persona's ChromaDB collection (best-effort).
3. Clears ``wizard_state.yaml`` (best-effort).

The handler publishes ``ONBOARDING_COMPLETE`` after ``finalize_wizard``
returns successfully.

Partial progress is durable: if the process crashes mid-wizard, state is
restored on next launch and the user resumes at their last completed step.

Public API surface is deliberately small — everything the frontend, startup,
and tests need is re-exported here.
"""

from src.onboarding.finalizer import FinalizeError, finalize_wizard
from src.onboarding.handler import register_wizard_handlers
from src.onboarding.state import (
    TelemetryPrefs,
    WizardState,
    WizardStep,
    clear_wizard_state,
    load_wizard_state,
    save_wizard_state,
)
from src.onboarding.validators import (
    CANONICAL_ARCHETYPES,
    CANONICAL_AVATAR_IDS,
    validate_archetype,
    validate_avatar,
    validate_display_name,
    validate_llm_provider,
    validate_terms_acceptance,
    validate_voice_mode,
)

__all__ = [
    "CANONICAL_ARCHETYPES",
    "CANONICAL_AVATAR_IDS",
    "FinalizeError",
    "TelemetryPrefs",
    "WizardState",
    "WizardStep",
    "clear_wizard_state",
    "finalize_wizard",
    "load_wizard_state",
    "register_wizard_handlers",
    "save_wizard_state",
    "validate_archetype",
    "validate_avatar",
    "validate_display_name",
    "validate_llm_provider",
    "validate_terms_acceptance",
    "validate_voice_mode",
]
