# Handoff — Continue the companion build (2026-04-30)

**Written:** 2026-04-29 (autonomous continuation run).
**Branch state:** `dev`, **2 commits ahead of origin/dev** at SHA `b777749`.
**Push status:** **NOT authorized this session.** P1 (`c593e32`) and
P2 (`b777749`) are local. Treat the next push as a fresh
authorization decision.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track only (same as 2026-04-29).

---

## 0. Morning status

1. `dev` is 2 commits ahead of `origin/dev` at `b777749`.
2. Working tree clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **57 / 57** (was 51; +6 model-swap)
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **66 / 66** (was 54; +6 model-swap registry, +6 cache)
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **41 / 41**

## 1. What landed in the most recent run

| SHA | Subject |
| --- | --- |
| `c593e32` | feat(l4,apps/desktop): in-provider vision model selection |
| `b777749` | feat(apps/desktop): TTL cache + manual refresh for vision model lists |

Reports:

- [P1_IN_PROVIDER_MODEL_SELECTION_EXECUTION_REPORT_2026-04-29.md](file:///C:/Users/dbhav/Projects/aether/P1_IN_PROVIDER_MODEL_SELECTION_EXECUTION_REPORT_2026-04-29.md)
- [P2_VISION_MODEL_CACHE_EXECUTION_REPORT_2026-04-29.md](file:///C:/Users/dbhav/Projects/aether/P2_VISION_MODEL_CACHE_EXECUTION_REPORT_2026-04-29.md)

## 2. Multimodal product surface today

End-to-end story, ground up:

1. **Local-only media permissions.** `MediaPermissions { camera,
   screen }` tri-state persisted at
   `<app_data>/media_permissions.json`; capture sites consult
   `evaluate_media_permission(kind) -> CaptureGate`.
2. **Camera + Screen capture surfaces.** `CameraPanel` and
   `ScreenPanel` wrap `getUserMedia`/`getDisplayMedia` behind
   start/stop/sample-frame, OS picker drives screen-source
   selection, single-shot only, default OFF.
3. **`analyze_frame` Tauri command.** Permission gate → policy audit
   through `TurnEngine` → memory write tagged `[frame analysis ·
   …]` → presence transitions → telemetry.
4. **Vision provider registry.** `VisionRegistry` on AppState holds
   zero or more `VisionProvider` impls + an active selection
   persisted at `<app_data>/vision_provider.json`. Adapters:
   `OllamaVisionProvider` (gated by `ollama-provider`) and
   `LlamaCppVisionProvider` (gated by `vision-llamacpp`).
   `analyze_frame::maybe_apply_vision` substitutes the text-only
   model output with the active vision provider's response.
5. **Per-provider model selection (NEW, P1 of 2026-04-29).** The
   `VisionProvider` trait exposes `set_model` and `current_model`.
   Both Ollama and llama.cpp adapters hold the model id behind
   `RwLock<String>`. The shell's `set_active_vision_model` Tauri
   command validates against the cached model list, applies the
   pick, and persists it under
   `vision_provider.json::model_per_provider` so a future provider
   swap restores each provider's last pick.
6. **Vision UI.** `VisionBadge` shows the active route, lets the
   user swap providers via dropdown, and lists each provider's
   models as **clickable chips**. The active model gets a green
   ring; others highlight on hover. A small `↻` refresh button next
   to the strip forces a cache-bypass refetch when the user has
   `ollama pull`'d a new model.
7. **Cached model lists (NEW, P2 of 2026-04-29).** `list_vision_models`
   sits behind a per-provider TTL cache (default 60 s).
   `set_active_vision_model` and `set_active_vision_provider`
   invalidate the relevant slot on swap so the user sees their pick
   immediately. `refresh_vision_models` forces a refetch.
8. **Per-panel cue history.** Each panel keeps the last 5 cues that
   produced a `frame_analyzed` outcome in `localStorage`.
9. **Trust drawer.** History tab carries a Media-only filter pill +
   a green "Ollama vision" / "llama.cpp vision" badge on rows
   served by a vision provider. Audit tab remains a clean
   provider-agnostic policy view (intentional contract).

## 3. What to build next — multimodal track

### Priority 1 — VisionBadge component test (P3 carried over)

`VisionBadge`'s state machine is now richer (loading → models →
swap-provider → swap-model → refresh) and the pure layers underneath
are fully covered. The badge itself is still uncovered by Vitest.

**Suggested shape**

- Add `@testing-library/react` (deliberate tooling addition; weigh
  before installing — it's the first React test dep in the app).
- Cover transitions:
  - status loading → text-only fallback (no providers)
  - status loading → providers visible, model strip loading → models
    visible, active ring on the right chip
  - click chip → mock `set_active_vision_model` → strip re-renders
    with new active ring
  - click `↻` → mock `refresh_vision_models` → re-render
  - error path: `setActiveVisionModel` rejects → red error line
    appears, dropdown re-enables
- Mock the `@tauri-apps/api/core` `invoke` shim through a Vitest
  module mock; the existing tests already work without a real
  Tauri runtime.

**Decision deferral note (2026-04-29):** I held off because P1+P2
already moved a lot of glass and adding RTL deserves its own scope
discussion (does Don want RTL or would a thin layer like
react-testing-vanilla be enough? Will the picker exercise drive
e2e too?). Land in a follow-up, not as a quiet add-on.

### Priority 2 — Per-provider TTL override env var

The 60 s cache TTL is a guess. If Don is iterating on a remote
llama-server with a slow `/v1/models`, a 60 s cache plus the manual
`↻` is fine; on Ollama a 5 s TTL would be just as good. Easy add:
`AETHER_VISION_MODEL_TTL_SECS` parsed in `main.rs`,
`ModelListCache::with_ttl` already supports it. **Defer** unless Don
asks — premature to optimize without a real workload.

### Priority 3 — Per-panel "active model" indicator

The CameraPanel and ScreenPanel already show the VisionBadge. The
current model is now in `VisionStatus.active_model`; the panels
could surface a one-line "→ llava:latest" hint above the Analyze
button so the user knows what model the next call will use without
scrolling to the badge. Tiny UX win; optional.

### Priority 4 — Privacy posture × remote vision

Wait for a third (remote) vision adapter; cheap to land then.

### Priority 5 — Microphone consent (separate track)

Out of scope for the multimodal vision foundation; mirror the
permission tri-state when the voice/STT path lands.

## 4. Risks / things to review first

- **`vision_provider.json` is now a 2-field shape.** `active` (old)
  + `model_per_provider` (new). Old files keep loading because
  `model_per_provider` has a serde default. New writers always emit
  both fields. Any future field MUST default-safe on read.
- **`MEDIA_TURN_KINDS` and `VISION_PROVIDER_IDS` are dual contracts**
  with the Rust outcomes / `VisionProvider::id()` returns. Adding a
  new media outcome or a new vision adapter requires updating both
  sides in the same change. The Vitest contract tests catch the
  mismatch immediately.
- **Audit tab still has no vision provenance.** Intentional — L5's
  `AuditRecordEvent` doesn't carry L4 provider info. The History
  tab badge is the right surface. Keep as-is unless Don explicitly
  calls for an L5 contract change.
- **Vitest pinned to ^2.** Vite 5 + Vitest 4 are incompatible.
  Bumping Vitest will require bumping Vite first.
- **In-flight `analyze_frame` keeps the provider AND model it
  captured.** Hot swap is per-call, not per-turn. This is the
  desired behaviour; document if Don ever wants stricter per-turn
  semantics.
- **`set_model` on the trait has a default `Ok(())`** — passive
  adapters silently no-op. Implementors that DO support runtime
  swap must override; `current_model()` defaults to `None`. Future
  read-only adapters get the right behaviour for free.
- **Cache TTL is 60 s.** A model added to the daemon mid-session
  won't appear until TTL expiry OR the user clicks `↻`. Current
  UX banks on the manual refresh as the escape hatch.

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
- `dev` is 2 commits ahead of `origin/dev` at `b777749`.
- Push is NOT pre-authorized this session. Ask first if you think
  pushing is needed.
- All multimodal vision-track work through 2026-04-29 has shipped
  AND committed locally; nothing has been pushed.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-04-30_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30` to confirm the picture.
3. Read these reports for shape context:
   - `P1_IN_PROVIDER_MODEL_SELECTION_EXECUTION_REPORT_2026-04-29.md`
   - `P2_VISION_MODEL_CACHE_EXECUTION_REPORT_2026-04-29.md`
   - `P3_TRUST_VISION_ANNOTATION_EXECUTION_REPORT_2026-04-27.md`
4. Skim:
   - `packages/l4-router/src/vision.rs` — VisionProvider trait
     surface (now includes set_model + current_model).
   - `packages/l4-router/src/providers/ollama_vision.rs` and
     `llamacpp_vision.rs` — RwLock<String> model patterns.
   - `apps/desktop/src-tauri/src/vision_registry.rs` — registry +
     persistence (model_per_provider).
   - `apps/desktop/src-tauri/src/vision_cache.rs` — pure TTL cache.
   - `apps/desktop/src/components/VisionBadge.tsx` — clickable
     model strip + refresh button.

Session focus (multimodal / vision assistant track ONLY):

P1 (carried) — VisionBadge component test
  - Decide first whether @testing-library/react is the right
    introduction for this app's first React test dep. If yes:
    - Install @testing-library/react and @testing-library/dom; pin
      to versions compatible with the existing Vitest ^2 + jsdom
      stack.
    - Mock @tauri-apps/api/core invoke through Vitest module
      mocks; cover at minimum:
      - status loading → text-only fallback when no providers.
      - status loading → providers visible, model strip loading
        → models visible with the active ring on the right chip.
      - click chip → setActiveVisionModel resolves → strip
        re-renders with the new active ring.
      - click ↻ → refreshVisionModels resolves → strip re-renders.
      - setActiveVisionModel rejects → red error line appears.
  - If no: document the deferral in the next handoff.

P2 — Per-panel "active model" indicator (optional)
  - Above the Analyze button in CameraPanel and ScreenPanel,
    show "→ <active_model>" pulled from vision_status when an
    active vision provider is configured. Hide in text-only mode.
  - Tests: extend mediaTurns / cueHistory tests if they touch
    the panel's prop surface.

P3 — Per-provider TTL override env var (optional)
  - Read AETHER_VISION_MODEL_TTL_SECS in main.rs; fall back to
    DEFAULT_TTL when unset/malformed.
  - Plumb through ModelListCache::with_ttl.
  - Tests: pure parse helper unit-tested in main.rs.

Hard constraints (don't drift):
- No push without explicit user authorization.
- No release / distribution / signing work.
- No streaming or continuous capture modes.
- No microphone / voice / STT / TTS work.
- No broad settings redesign.
- Do NOT unify LlamaCppConfigError + OllamaConfigError across the
  feature boundary.
- Do NOT extend L5's AuditRecordEvent to carry provider info.
- Do NOT change the durable-memory privacy posture for images
  (image bytes stay transient).
- Do NOT change the analyze_frame trust/audit contract.
- Do NOT widen the vision_provider.json contract beyond
  additive-default-safe shapes.

Process for each priority:
1. Implement.
2. Run focused tests for the touched layer.
3. Run the full check set:
   - cargo fmt --all -- --check
   - cargo check --workspace
   - cargo test --workspace
   - cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp
   - apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp
   - python tools/lint-layer-boundaries/check.py
   - apps/desktop && pnpm typecheck && pnpm build && pnpm test
4. Fix all failures.
5. Commit in clear scoped slices.

Before stopping:
- Keep git status clean.
- Write/update execution reports for each priority you touch.
- Write a fresh handoff file with the same structure as
  HANDOFF_2026-04-30_CONTINUE_COMPANION_BUILD.md: morning status,
  commits this run, reports, what the product does now, next
  priorities ordered with suggested shapes, risks, and a copy-paste
  recommended next prompt.
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
