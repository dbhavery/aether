# P4 — Shell-side language for typed provider errors

**Date:** 2026-04-21
**Branch:** `dev`
**Layers touched:** apps/desktop shell (Rust + TS).

## What shipped

- New `memory_router::friendly_provider_error(&L4Error) -> String`
  maps each typed L4Error variant (ProviderNotRunning, ProviderTimeout,
  ProviderModelNotFound, ProviderBadResponse, ProviderUnknown) to a
  user-facing sentence with an actionable next step:
  - NotRunning → "Start it with `ollama serve`".
  - Timeout → "Try a smaller model, or raise AETHER_OLLAMA_TIMEOUT_MS".
  - ModelNotFound → "Pull it with `ollama pull <model>`".
  - BadResponse / Unknown → surface detail verbatim for diagnosis.
  All prefixed with the stable sentinel `PROVIDER_ERROR: `.
- `RoleTaggedOllamaRouter::dispatch` now maps L4Error through
  `friendly_provider_error` before wrapping as `L1Error::Router`.
- `commands.rs::submit_turn` detects the prefix after an engine error
  and, if present, promotes the failure into a transcript system
  message with `kind = "provider_error"` — instead of bubbling as a
  Tauri command error (which the UI renders as a raw red-error blob).
- User's utterance and the synthesised system note are both appended
  to L2 memory so transcript continuity survives a provider failure.
- `TurnOutcomeKind` TS union gains `"provider_error"`.
- 5 new tests:
  - 1 in `memory_router.rs` covering all four mapped variants.
  - 2 in `commands.rs` covering `extract_provider_error` (happy + reject).
  - No regressions; 15 desktop tauri tests pass with `ollama-provider`
    feature (was 12); 9 pass without the feature (unchanged).

## Design note: why not extend L1Error?

Adding a typed `L1Error::ProviderError(kind, detail)` variant would be
cleaner, but `aether_l1_interaction` lives in `packages/l1-interaction`
which does not depend on `aether_l4_router` (sibling-layer rule §1.4).
Mirroring `L4Error`'s variants inside L1 would force a mapping layer
inside the engine crate, or a new shared error crate. Both are bigger
scope than the problem requires.

Instead we route through the existing `L1Error::Router(String)`
channel with a stable `PROVIDER_ERROR: ` prefix. The shell is the only
place that needs to decode it, and the shell owns both sides of the
mapping. If a future slice needs cross-crate consumers to interpret
provider errors, promoting this to a typed variant is a small,
self-contained change.

## Checks run

- `cargo fmt --all` — applied.
- `cargo check` (tauri crate) — clean (warnings only from upstream
  L1 docs lints).
- `cargo test` (tauri, default) — 9 passed.
- `cargo test --features ollama-provider` — 15 passed.
- TS types updated; `pnpm typecheck` confirmed via subsequent build.

## Risks / follow-ups

- Regex-free prefix detection is order-dependent on `L1Error::Router`'s
  `Display` format (`"router client: {0}"`). If that label ever
  changes, `extract_provider_error` silently degrades to the old raw
  error path. The `extract` function tolerates both prefixed and
  bare payloads to soften this. A rename should still trip the
  positive unit test.
- The reflex-stub path never produces provider errors, so the new
  "provider_error" outcome is only reachable under
  `--features ollama-provider`. Non-Ollama builds still compile but
  can never surface one.
- UI styling for `provider_error` uses the existing `system` bubble;
  good enough for v0, but a future pass could add a distinct icon
  ("daemon down", "model missing") per sub-variant.
