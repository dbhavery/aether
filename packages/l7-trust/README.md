# @aether/l7-trust

**Status:** Wave 4 stub. Backend surfaces only — the React UI lives in `apps/desktop/` (future wave).

L7 owns trust UX + onboarding + shell adapter. This crate is the Rust-side contract; implementations live in the desktop shell.

## References

- `ARCHITECTURE.md` — the L7 trust + onboarding layer.
- `docs/ONBOARDING-SPEC.md` — the onboarding flow.

## Wave 4 contents

- `ApprovalPrompt`, `PostureBanner` — shapes pushed to the shell.
- `OnboardingScreen` (8) + `OnboardingState`.
- `ShellAdapter` trait — implemented once by `apps/desktop/` (Tauri primary).
- `L7Error`.

## Next wave

Wave 5+ — onboarding state machine driver, approval-renderer integration tests against `DefaultPolicyEngine`, posture-banner event coalescing, Tauri shell adapter.
