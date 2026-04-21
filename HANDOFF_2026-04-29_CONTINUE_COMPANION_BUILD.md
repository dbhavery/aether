# Handoff — Continue the companion build (2026-04-29)

**Written:** 2026-04-27 (autonomous continuation run, expanded after push).
**Branch state:** `dev`, **pushed to origin/dev** at SHA `dfb815b`.
**Push status:** **AUTHORIZED + EXECUTED this session.** All 23
prior local commits are now on the remote. Treat further pushes as
a fresh authorization decision.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track only.

---

## 0. Morning status

1. `dev` is in sync with `origin/dev` at `dfb815b`.
2. Working tree clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **51 / 51** (was 45; +6 model parse)
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **54 / 54**
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **41 / 41** (vitest, 18 cue +
     23 media-turn / vision-provider helpers)

## 1. What landed in the most recent run

| SHA       | Subject |
| --------- | ------- |
| `bd51e65` | test(apps/desktop): vitest harness + cue history & media-turn tests |
| `e50a8f1` | feat(l4,apps/desktop): per-provider model discovery in vision dropdown |
| `fd400c2` | feat(apps/desktop): vision-provider annotation in Trust drawer History |
| `dfb815b` | docs: 2026-04-27 vision-strengthening reports + 2026-04-29 handoff |

Reports:

- [P1_VITEST_HARNESS_EXECUTION_REPORT_2026-04-27.md](file:///C:/Users/dbhav/Projects/aether/P1_VITEST_HARNESS_EXECUTION_REPORT_2026-04-27.md)
- [P2_MODEL_DISCOVERY_EXECUTION_REPORT_2026-04-27.md](file:///C:/Users/dbhav/Projects/aether/P2_MODEL_DISCOVERY_EXECUTION_REPORT_2026-04-27.md)
- [P3_TRUST_VISION_ANNOTATION_EXECUTION_REPORT_2026-04-27.md](file:///C:/Users/dbhav/Projects/aether/P3_TRUST_VISION_ANNOTATION_EXECUTION_REPORT_2026-04-27.md)

## 2. Multimodal product surface today

End-to-end story, ground up:

1. **Local-only media permissions.** `MediaPermissions { camera,
   screen }` tri-state (`Allow` / `Ask` / `Deny`) persisted at
   `<app_data>/media_permissions.json`. Wired into AppState; gated
   by `evaluate_media_permission(kind) -> CaptureGate`. Settings
   drawer exposes the controls. See
   [`docs/MEDIA-PERMISSIONS.md`](file:///C:/Users/dbhav/Projects/aether/docs/MEDIA-PERMISSIONS.md).
2. **Camera + Screen capture surfaces.** `CameraPanel` and
   `ScreenPanel` wrap the browser `MediaDevices`/`getDisplayMedia`
   APIs behind start/stop/sample-frame, default OFF, OS picker
   drives screen-source selection, single-shot only.
3. **`analyze_frame` Tauri command.** Permission gate → policy
   audit through `TurnEngine` (capability is `MediaCamera` /
   `MediaScreenCapture` at `Auto/Medium`, audited via L5) → memory
   write tagged `[frame analysis · camera] <cue>` → presence
   transitions → telemetry.
4. **Vision provider registry.** `VisionRegistry` on AppState holds
   zero or more `VisionProvider` impls + an active selection
   persisted at `<app_data>/vision_provider.json`.
   `OllamaVisionProvider` (gated by `ollama-provider`) and
   `LlamaCppVisionProvider` (gated by `vision-llamacpp`) implement
   the trait. `analyze_frame::maybe_apply_vision` substitutes the
   text-only model output with the active vision provider's
   response when one is configured.
5. **Vision UI.** `VisionBadge` shows the active route, lists every
   registered provider in a dropdown for runtime swap, and surfaces
   the active provider's available models via the new
   `list_vision_models` command (Ollama `/api/tags`, llama.cpp
   `/v1/models`). Model selection inside a provider is the next
   step.
6. **Per-panel cue history.** Camera and screen each remember the
   last 5 cues that produced a `frame_analyzed` outcome, kept in
   `localStorage` (never durable memory).
7. **Trust drawer.** History tab carries a Media-only filter pill
   plus a green "Ollama vision" / "llama.cpp vision" badge on rows
   served by a vision provider. Audit tab remains a clean
   provider-agnostic policy view (intentional contract).

## 3. What to build next — multimodal track

### Priority 1 — In-provider model selection

The dropdown shows what's available; selecting a specific model on
a provider is the natural next step.

**Suggested shape**

- Extend the `VisionProvider` trait with
  `fn set_model(&self, id: &str) -> Result<(), L4Error>`. Default
  impl returns `Ok(())` so adapters that can't change models
  inherit a no-op without breaking.
- Implement `set_model` on `OllamaVisionProvider` and
  `LlamaCppVisionProvider` using interior mutability
  (`RwLock<String>`) on the model field of their config.
- New Tauri command `set_active_vision_model(id: String)` calls
  `set_model` on the active provider only. Unknown ids relative to
  the most-recent `list_models()` snapshot should reject up front.
- Persist alongside `vision_provider.json` — extend the wire shape
  to `{ active: "ollama-vision", model_per_provider: { "ollama-vision": "llava:latest" } }`
  so the per-provider model survives a provider swap.
- Fallback: if the persisted model is no longer in the daemon's
  model list, fall back to the daemon-selected default and warn.

**UI**

- Promote the model strip in `VisionBadge` from chips to a small
  `<select>` (or keep the chip strip and add an "Active" indicator
  + click-to-pick).
- Persistence and swap semantics mirror the provider swap (per-call
  hot swap, in-flight `analyze_frame` keeps captured handle).

**Tests**

- L4: pure tests for `set_model` round-trip on each adapter.
- Shell: registry test that swapping the active provider and back
  preserves each provider's last model selection.

### Priority 2 — Short-lived model-list cache + manual refresh

`list_vision_models` re-fetches from the daemon every time the
active provider changes, which is fine on Ollama but expensive on
remote daemons.

**Suggested shape**

- Cache the most recent `Vec<String>` per `provider_id` with a
  monotonic timestamp. TTL ~60 s. Invalidate on `set_model` so the
  user immediately sees their pick.
- New Tauri command `refresh_vision_models()` forces a re-fetch
  bypassing the cache.
- UI: add a small `↻` button next to the model strip that calls
  the refresh command.

### Priority 3 — Optional `VisionBadge` component test

Pure layers are covered. `VisionBadge` has a non-trivial state
machine (status-loading → providers / model-loading → models /
error). A small Vitest + `@testing-library/react` test would lock
the loading → success and loading → error transitions.

**Scope decision** Adding `@testing-library/react` is a deliberate
tooling addition; only land if the trade-off feels right at the
time. Otherwise document as deferred.

### Priority 4 — Privacy posture × remote vision

Wait for a third (remote) vision adapter; cheap to land then.

### Priority 5 — Microphone consent (separate track)

Out of scope for the multimodal vision foundation; mirror the
permission tri-state when the voice/STT path lands.

## 4. Risks / things to review first

- **`MEDIA_TURN_KINDS` and `VISION_PROVIDER_IDS` are dual contracts**
  with the Rust outcomes / `VisionProvider::id()` returns. Adding a
  new media outcome or a new vision adapter requires updating both
  sides in the same change. The Vitest contract tests will catch
  the mismatch immediately.
- **Audit tab still has no vision provenance.** Intentional — L5's
  `AuditRecordEvent` doesn't carry L4 provider info. The History
  tab badge is the right surface. If you want Audit to know, that's
  a deliberate L5 contract change.
- **`vision_provider.json` is an additive contract.** Once shipped,
  any new field must default safely on read. The recommended P1
  shape (`model_per_provider`) is already additive — old files
  without that field default to `None` per provider.
- **Vitest pinned to ^2.** Vite 5 + Vitest 4 are incompatible.
  Bumping Vitest will require bumping Vite first.
- **In-flight `analyze_frame` keeps the provider it captured.** Hot
  swap is per-call, not per-turn. This is the desired behaviour;
  document if Don ever wants stricter per-turn semantics.

## 5. Recommended next prompt (copy-paste, detailed)

A more detailed version of the embedded prompt — paste this into the
next session as-is.

---

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state:
- `dev` is in sync with `origin/dev` at `dfb815b`.
- Push is NOT pre-authorized this session. Ask first if you think
  pushing is needed.
- All multimodal vision-track work through 2026-04-27 has shipped
  AND pushed.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-04-29_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30` to confirm the picture.
3. Read these reports for trait + UI shape context:
   - `P2_MODEL_DISCOVERY_EXECUTION_REPORT_2026-04-27.md`
   - `P3_TRUST_VISION_ANNOTATION_EXECUTION_REPORT_2026-04-27.md`
   - `P2_VISION_RUNTIME_SWAP_EXECUTION_REPORT_2026-04-26.md`
4. Skim:
   - `packages/l4-router/src/vision.rs` — VisionProvider trait.
   - `packages/l4-router/src/providers/ollama_vision.rs` and
     `llamacpp_vision.rs` — adapter shapes.
   - `apps/desktop/src-tauri/src/vision_registry.rs` — registry +
     persistence wire shape.
   - `apps/desktop/src/components/VisionBadge.tsx` — model strip /
     dropdown UI.

Session focus (multimodal / vision assistant track ONLY):

P1 — In-provider model selection
  - Extend `VisionProvider` trait with
    `fn set_model(&self, id: &str) -> Result<(), L4Error>`.
    Default impl returns `Ok(())` so passive adapters inherit a
    no-op.
  - Implement on `OllamaVisionProvider` and `LlamaCppVisionProvider`
    using `RwLock<String>` (or a similarly cheap interior-mutability
    pattern) on the model field. Healthcheck and analyze must
    pick up the swapped model.
  - Tests:
    - Adapter unit: set_model round-trip, healthcheck and
      `build_vision_payload` reflect the new model.
    - Registry / persistence test: swapping the active provider
      and back preserves each provider's last model.
  - New Tauri command `set_active_vision_model(id: String)` calls
    `set_model` on the active provider only. Unknown ids relative
    to the most recent `list_vision_models` snapshot should
    reject upfront. Persist the pick alongside `vision_provider.json`
    in an additive shape, e.g.:
        {
          "active": "ollama-vision",
          "model_per_provider": {
            "ollama-vision": "llava:latest"
          }
        }
    Old files without `model_per_provider` must keep loading.
  - Frontend:
    - Promote the model strip in `VisionBadge` to indicate the
      active model and let the user click a chip to switch
      (preferred) OR add a small `<select>` next to it.
    - Hot-swap semantics: per-call (next `analyze_frame` uses the
      new model; in-flight calls keep their captured handle).
  - Acceptance: pnpm test still green, cargo tests still green,
    set_model round-trip locked by both unit + persistence tests.

P2 — Short-lived model-list cache + manual refresh
  - Cache `Vec<String>` per `provider_id` with a monotonic
    timestamp; TTL ~60 s. Invalidate on `set_model` so the user
    sees their pick immediately.
  - New Tauri command `refresh_vision_models()` forces a
    cache-bypassing re-fetch.
  - UI: a small `↻` refresh button next to the model strip in
    `VisionBadge` calls the refresh command and re-renders.
  - Tests: cache hit/miss / TTL expiry as a small unit test on a
    pure cache helper.

P3 — Optional only if time:
  - Add a small Vitest + @testing-library/react component test
    for `VisionBadge`'s state machine — cover loading → models
    and loading → error. Decide whether the dependency is worth
    it before installing.

Hard constraints (don't drift):
- No push without explicit user authorization.
- No release / distribution / signing work.
- No streaming or continuous capture modes.
- No microphone / voice / STT / TTS work.
- No broad settings redesign.
- Do NOT unify `LlamaCppConfigError` + `OllamaConfigError` across
  the feature boundary.
- Do NOT extend L5's `AuditRecordEvent` to carry provider info
  unless explicitly required by the targeted tasks (it isn't this
  run).
- Do NOT change the durable-memory privacy posture for images
  (image bytes stay transient).
- Do NOT change the analyze_frame trust/audit contract.

Process for each priority:
1. Implement.
2. Run focused tests for the touched layer.
3. Run the full check set:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
   - `python tools/lint-layer-boundaries/check.py`
   - `apps/desktop && pnpm typecheck && pnpm build && pnpm test`
4. Fix all failures.
5. Commit in clear scoped slices.

Before stopping:
- Keep `git status` clean.
- Write/update execution reports for P1 and P2 (and P3 if you
  attempted it).
- Write a fresh handoff file with the same structure as
  `HANDOFF_2026-04-29_CONTINUE_COMPANION_BUILD.md`:
  morning status, commits this run, reports, what the product
  does now, next priorities ordered with suggested shapes,
  risks, and a copy-paste recommended next prompt.
- Confirm whether push is authorized for the run; if not, leave
  commits unpushed and note it in the handoff.

Final response format (return exactly this structure):

## Tasks completed
- ...

## Commits
- SHA — message

## Tests and checks
- ...

## Remaining multimodal backlog
1. ...
2. ...

## Decisions for review
1. ...
2. ...

## Next recommended prompt
```md
...
```

Stay strictly on the multimodal vision track. No drift.
```

---

(end of handoff)
