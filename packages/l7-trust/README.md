# @aether/l7-trust

**Status:** Wave 4 stub. Backend surfaces only — the React UI lives in `apps/desktop/` (future wave).

L7 owns trust UX + onboarding + shell adapter. This crate is the Rust-side contract; implementations live in the desktop shell.

## References

- `ARCHITECTURE.md` — the L7 trust/onboarding layer.
- `docs/ONBOARDING-SPEC.md` — the trust UX and onboarding flow.

## Wave 4 contents

- `ApprovalPrompt`, `PostureBanner` — shapes pushed to the shell.
- `OnboardingScreen` (8) + `OnboardingState`.
- `ShellAdapter` trait — implemented once by `apps/desktop/` (Tauri primary).
- `L7Error`.

## L7.1 contents (`approval` module)

Minimal, synchronous approval-resolution surface used by the current CLI/demo to turn a `Decision::Ask` into a real accept/reject loop — the first user-facing trust control.

- `ApprovalResolution { Approve, Reject }` — narrow first-slice outcomes.
- `ApprovalSurface` trait — `fn resolve(&self, prompt: &ApprovalPrompt) -> Result<ApprovalResolution, L7Error>`.
- `CliApprovalSurface` — stdout render + stdin line read; accepts `y / yes / approve / a` (case-insensitive), rejects everything else.
- `FixedApprovalSurface(ApprovalResolution)` — deterministic test double.
- `resolution_to_user_choice` — maps to `aether_l5_policy::UserChoice`.
- `build_approval_response` — builds a ticket-scoped `ApprovalResponse` ready for `PolicyEngine::respond_approval`.
- `approval_prompt_from_ticket` — builds a renderable `ApprovalPrompt` from a ticket.
- `render_approval_block` — deterministic terminal rendering of ticket / capability / scope / reason.
- `human_capability` / `human_scope` — stable labels for the full `Capability` taxonomy and all `ResourceScope` variants.

**Out of scope for L7.1:** scope narrowing UI, duration pickers, defer-to-draft, re-auth tokens for Critical capabilities, trust-centre dashboard, audit surfacing, posture-banner wiring. The types to support those already live in L5 (`UserChoice::AllowScope`, `AllowTask`, `AllowSession`, `DeferToDraft`; `ApprovalResponse::reauth_token`, `duration_override`) and can be wired in without breaking this trait — add a variant to `ApprovalResolution` and extend the map function.

## Next wave

Wave 5+ — onboarding state machine driver, posture-banner event coalescing, Tauri shell adapter, richer approval variants (scope / duration / defer-to-draft), trust-centre screens.
