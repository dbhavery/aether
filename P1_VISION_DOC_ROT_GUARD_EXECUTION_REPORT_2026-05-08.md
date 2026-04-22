# P1 — Vision V1 architecture-doc rot guard — execution report (2026-05-08)

**Status:** Shipped locally on `dev`. Push not authorized.

## Goal

Make it mechanically harder for `docs/VISION-V1-ARCHITECTURE.md` to
drift away from the code and contracts it describes. The doc is
valuable precisely because future tracks (remote vision, voice, L3
presence, L2 memory) will design against it — a quietly wrong
reference is worse than no reference at all.

The 2026-05-06 Chunk C report already flagged this risk:
> "If we routinely forget, fold it into a CI check that fails when
> `docs/VISION-V1-ARCHITECTURE.md` hasn't been touched in the same
> commit as files it references."

That approach is too coarse (false positives for any incidental
change to a referenced file). This round ships a tighter,
manifest-based guard instead.

## Design

A single Python script at `tools/lint-vision-doc/check.py` carries a
**curated anchor manifest**. Each anchor is a (kind, file, needle)
triple claiming the doc depends on that thing existing in code.
Kinds:

- **FILE** — a file path must resolve.
- **SYMBOL** — a literal substring (e.g. `fn analyze_frame`,
  `struct VisionRequest`, `MEDIA_TURN_KINDS`) must appear at least
  once in the named file.
- **STRING** — a literal token (telemetry kind, env var name,
  provider id, config filename) must appear at least once in the
  named file.

Plus a header check: the doc must have a parseable
`**Status:** Current as of YYYY-MM-DD.` line near the top.

51 anchors across 12 files today. The manifest is deliberately
curated, not auto-extracted from the doc — a parser would be
fragile, and the point is to force a human to acknowledge the
contract when it changes.

### Why a manifest, not a doc parser?

A parser can match strings in prose but can't distinguish "this is
a cross-boundary contract" from "this is an incidental code
reference the prose happens to mention." The manifest encodes the
human judgment about what the doc is actually promising.

### Why not hook into `cargo test` or `pnpm test`?

This is a doc linter, not a code test. A test failing for doc
drift would be confusing. A doc-specific linter is honest about its
scope, runs fast, and can be added to CI independently.

### Why no staleness/date comparison?

Filesystem mtimes reset on checkout; git timestamps require `git`
on PATH and introduce a second failure mode. The `Status:` header
exists and a human updates it when they update the manifest — that
is the date check. Mechanizing it further is not worth the
complexity right now.

## Surfaces touched

- `tools/lint-vision-doc/check.py` — new 280-line script, stdlib
  only. Pattern mirrors `tools/lint-layer-boundaries/check.py`
  (argparse, `--json`, shared `_repo_root` logic, cleanly
  human/JSON separable output).
- `tools/lint-vision-doc/README.md` — operator guide: what it
  checks, what it doesn't, how to resolve failures, when to extend
  the manifest.
- `docs/VISION-V1-ARCHITECTURE.md`:
  - New **§11 "Rot guard"** section describing what the guard
    does, what it doesn't, and the four-step contract for updating
    doc + manifest + status date.
  - **§10 "Reference reports"** refreshed to include the 2026-05-06
    chunk reports, the 2026-05-07 P1 decision report, and this
    report.
  - Status line already bumped to `2026-05-07` yesterday; no
    further date change today since the prose updates are
    additive (documenting the new guard, not changing anything
    the doc claims about code).

## Anchors covered

| Section | Anchors | Why they matter |
| --- | --- | --- |
| §1 flow | `analyze_frame`, `maybe_apply_vision`, `validate_frame_data_url`, `record_frame_early_exit_telemetry`, `MIN_FRAME_BODY_LEN` | The contract the TS shell relies on |
| §2 providers | `VisionProvider` trait, `VisionRequest`, `VisionResponse`, `OllamaVisionProvider`, `LlamaCppVisionProvider`, their config structs, provider ids (`ollama-vision`, `llamacpp-vision`), env vars | Cross-boundary identity + configuration |
| §3-4 persistence | `VisionPersistedState`, `vision_persistence_path_for`, `auto_select_first_if_unset`, `vision_seed_missing_models`, `seed_missing_models_from_adapters`, `vision_provider.json` literal, `ModelListCache`, `AETHER_VISION_MODEL_TTL_SECS` | Selection rules + TTL cache behavior |
| §6 telemetry | `frame_analyzed`, `frame_blocked`, `frame_invalid`, `permission_denied`, `permission_ask` — each checked in BOTH `commands.rs` AND `mediaTurns.ts` | Five-kind parity across Rust ↔ TS |
| §7 UI | `VISION_PROVIDER_REGISTRY`, `truncateMiddleForDisplay`, `VisionBadge.tsx`, `TrustDrawer.tsx` + `kindClass` | User-visible surfaces |

## One miss caught during the run

The first run failed on the `vision_seed_missing_models` anchor —
the symbol lives in `apps/desktop/src-tauri/src/state.rs` (the
`AppState` wrapper that delegates to
`VisionRegistry::seed_missing_models_from_adapters`), not in
`vision_registry.rs` directly. The manifest was corrected and the
registry-side function added as a second anchor so both names are
tracked. This is exactly the kind of quiet split the guard is
supposed to catch — and it did, immediately on first run.

## How to resolve a future failure

Four cases, covered in the README:

1. Symbol renamed/deleted without updating the doc → restore, OR
   update doc + manifest + bump status date.
2. Doc gained a new anchor but manifest didn't → add the anchor
   entry.
3. File moved → update the path.
4. `Status:` header missing → add it back.

## Hard-constraint compliance

- No new vision providers.
- No remote-vision implementation.
- No mic/voice/STT/TTS work.
- No streaming / continuous capture.
- No image-persistence posture change.
- No `vision_provider.json` schema change.
- No `LlamaCppConfigError` / `OllamaConfigError` unification.
- No `AuditRecordEvent` change.
- No new test dependencies.
- No `analyze_frame` trust/audit contract change.
- No code behavior changed at all — this round is a doc linter plus
  documentation.

## Tests

Full check set run, all green:

- `cargo fmt --all -- --check` — clean
- `cargo check --workspace` — clean (2 pre-existing warnings in
  `aether-l1-interaction`, unchanged)
- `cargo test --workspace` — all test binaries green
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` — **57 / 57**
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` — **93 / 93**
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — **OK, 51 anchors across 12 files**
- `apps/desktop && pnpm typecheck` — clean
- `apps/desktop && pnpm build` — clean, `built in 1.82s`
- `apps/desktop && pnpm test` — **86 / 86**

## Self-test: does the guard actually fail when it should?

Yes. The initial run flagged the `vision_seed_missing_models`
location mismatch as a hard failure with the exact path + needle
in the output. After correcting the manifest (the intent of the
tool), the guard returned `OK`. No synthetic break-test was shipped
because the first real run exercised the failure path genuinely.

## How to extend

Add a new tuple to `ANCHORS` in `tools/lint-vision-doc/check.py`
whenever the doc starts naming a new file, symbol, or cross-boundary
string constant. The README documents the taste rule: do NOT add
anchors for implementation details the doc doesn't name, prose-level
descriptions, or ephemeral state.

## Future extensions worth considering (not shipped)

- Wire the guard into a lightweight CI workflow alongside the
  layer-boundary lint. Out of scope for this session — no CI config
  exists to extend today.
- Add a second pass that reads the doc and checks the
  **reverse** direction: every file or symbol mentioned in the doc
  should appear in the manifest. Would catch "prose drifted ahead
  of anchors" cases. Deferred as over-engineering for now.
- Promote the doc-linter harness to a shared `tools/lint/` umbrella
  once we have a third linter with similar shape (layer-boundary +
  policy-bypass + private-asset-leak + vision-doc = a pattern
  emerging).
