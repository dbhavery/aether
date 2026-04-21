# P2 — ts-rs vision-provider id codegen decision — execution report (2026-05-05)

**Status:** Decision-only. **Codegen continues to be deferred.** No
code changes. No commits other than this report + the next handoff.

## Current situation (verified this session)

- TS side: `apps/desktop/src/lib/visionProviders.ts` holds the
  canonical `VISION_PROVIDER_REGISTRY` (id + shortLabel) with two
  entries: `"ollama-vision"`, `"llamacpp-vision"`. Five downstream
  consumers (mediaTurns, ActiveVisionRoute, visionRouteSummary,
  Transcript footer dedup, badge derivation) all read from this
  registry. Adding a new TS-side id is one row.
- Rust side: `OllamaVisionProvider::id() -> "ollama-vision"` and
  `LlamaCppVisionProvider::id() -> "llamacpp-vision"` are still
  defined independently inside each adapter.
- Existing safety net: `vision_registry::tests` cover registration,
  fallback when the persisted active id is unknown, and per-provider
  model preservation across swaps. The TS registry has its own
  vitest coverage. A typo on either side would not compile-fail; it
  would surface as a runtime mismatch the next time the user picked
  the affected provider.

## Decision

**Codegen continues to be deferred.** Reasons (re-evaluated this
session, conclusion unchanged from 2026-05-03 and 2026-05-04):

1. **Two adapters means two strings to keep in lockstep.** The
   duplication cost is small; the bug surface is narrow.
2. **No drift biting in practice.** No test was fragile because of
   id duplication this session, no new TS call site of the registry
   was added, no Rust adapter renamed its id. The triggering
   condition (a third adapter, or a flurry of new call sites) has
   not appeared.
3. **Codegen carries a non-trivial fixed cost.** Build script or
   `ts-rs` / `specta` integration, generated-file checked-in vs.
   regenerated-on-build choice, CI freshness check, contributor
   workflow doc. With two sources to dedupe, the scaffolding costs
   more than the bug it prevents.

## Trigger conditions for picking it up later

When **any** of these become true, treat codegen as prerequisite
work for the next vision-track PR:

- A third vision adapter is being scoped (most likely trigger).
- TS registry consumers grow past ~7–8 (currently 5; today's count
  is comfortably below the line).
- Id drift bites in practice — i.e. a runtime mismatch ships, or a
  test author has to dual-update the same id in three places.
- A non-Rust workspace member (e.g. a future CLI, a Python tool)
  starts consuming the same id vocabulary. At that point a
  language-neutral source-of-truth (JSON schema + codegen)
  outranks `ts-rs`.

## Likely approach when the time comes

(Same as 2026-05-03 P3 deferral report; restated for convenience.)

- **`ts-rs` (or `specta`) with a shared Rust enum.** Define
  `VisionProviderId { OllamaVision, LlamaCppVision, ... }` once in
  Rust, derive serde + ts-rs, emit a generated TS const into
  `apps/desktop/src/lib/generated/`. CI re-runs codegen and fails
  on drift.
- **JSON schema source-of-truth** if the consumer set goes
  cross-language.

Decide between the two at the trigger moment, not now.

## Hard-constraint compliance

- No push.
- No code change in this report.
- No L5 / persistence / streaming changes.
- No new providers.
- No new test deps.
