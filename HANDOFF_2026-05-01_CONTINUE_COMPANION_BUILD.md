# Handoff — Continue the companion build (2026-05-01)

**Written:** 2026-04-30 (autonomous continuation run).
**Branch state:** `dev`, **6 commits ahead of origin/dev** at SHA `49d0648`.
**Push status:** **NOT authorized this session.** All six commits
since the last push are local. Treat the next push as a fresh
authorization decision.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track only (same as 2026-04-29 / -30).

---

## 0. Morning status

1. `dev` is 6 commits ahead of `origin/dev` at `49d0648`.
2. Working tree clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **66 / 66**
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **59 / 59** (was 41; +7 RTL,
     +8 ActiveVisionRoute, +3 visionRouteSummary)

## 1. What landed in the most recent run

| SHA | Subject |
| --- | --- |
| `81bc7e5` | test(apps/desktop): RTL component tests for VisionBadge |
| `06f2743` | feat(apps/desktop): per-panel active vision route hint above Analyze |
| `49d0648` | feat(apps/desktop): annotate Trust drawer media rows with vision model |

Reports:

- [P1_VISION_BADGE_RTL_TESTS_EXECUTION_REPORT_2026-04-30.md](file:///C:/Users/dbhav/Projects/aether/P1_VISION_BADGE_RTL_TESTS_EXECUTION_REPORT_2026-04-30.md)
- [P2_PER_PANEL_VISION_ROUTE_HINT_EXECUTION_REPORT_2026-04-30.md](file:///C:/Users/dbhav/Projects/aether/P2_PER_PANEL_VISION_ROUTE_HINT_EXECUTION_REPORT_2026-04-30.md)
- [P3_TRUST_DRAWER_MODEL_ANNOTATION_EXECUTION_REPORT_2026-04-30.md](file:///C:/Users/dbhav/Projects/aether/P3_TRUST_DRAWER_MODEL_ANNOTATION_EXECUTION_REPORT_2026-04-30.md)

Cumulative since the last push (`dfb815b` @ 2026-04-27 → now):

- `c593e32` in-provider vision model selection
- `b777749` TTL cache + manual refresh for vision model lists
- `67111c3` 2026-04-29 reports + handoff
- `81bc7e5` RTL component tests for VisionBadge
- `06f2743` per-panel active vision route hint
- `49d0648` Trust drawer media model annotation

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
5. **Per-provider model selection.** `VisionProvider` exposes
   `set_model` and `current_model`. Model id held behind
   `RwLock<String>` in both adapters. `set_active_vision_model`
   command validates against the cached model list, applies the
   pick, and persists per-provider picks under
   `vision_provider.json::model_per_provider`. Provider swap
   restores each provider's last pick.
6. **Cached model lists.** `list_vision_models` sits behind a
   per-provider TTL cache (default 60 s). `set_active_*`
   invalidates the active slot. `refresh_vision_models` forces a
   refetch.
7. **VisionBadge UI.** Provider dropdown + clickable model chips +
   `↻` refresh affordance + RTL component tests covering the
   user-visible state machine (text-only fallback, models loading,
   models visible, swap success, swap failure).
8. **Per-panel ActiveVisionRoute hint (NEW, P2 of 2026-04-30).**
   A small mono-spaced "→ <provider> · <model>" line above the
   Analyze button on both Camera and Screen panels. Three states
   (provider+model / provider-only / text-only fallback). Stays
   synchronised with the badge via an `onRouteChanged` callback.
9. **Per-panel cue history.** Each panel keeps the last 5 cues
   that produced a `frame_analyzed` outcome in `localStorage`.
10. **Trust drawer.** History tab carries the Media-only filter
    pill + a green "<provider> · <model>" badge on rows served by
    a vision provider (NEW, P3 of 2026-04-30) and the body line
    surfaces the model id. Audit tab remains a clean
    provider-agnostic policy view (intentional contract).

## 3. What to build next — multimodal track

### Priority 1 — Per-provider TTL override env var

The 60 s vision model-list cache TTL is a guess.
`AETHER_VISION_MODEL_TTL_SECS` parsed in `main.rs`,
`ModelListCache::with_ttl` already supports it. Trivial to land;
land only if Don actually wants to tune it. **Defer until requested.**

### Priority 2 — Persona transcript meta annotation

The `MessageMeta` struct on transcript messages already carries
`provider` and `tier` but not `model`. Today the assistant message
in the transcript shows the long tier label for vision turns. We
could surface the model in the transcript bubble's hover/footer
next to provider/latency/tokens. Minor consistency win between the
panels (which now show "→ provider · model"), the Trust drawer
(which now shows "provider · model"), and the transcript (which
still only shows provider + tier).

**Suggested shape:**
- Add `model: Option<String>` to `MessageMeta` and populate it from
  the same `vision_model` capture in `analyze_frame`.
- Surface in `Transcript.tsx` next to the existing provider/tier
  line.
- Keep it absent for text-only assistant turns.

### Priority 3 — Boot-time auto-select picks the persisted model

`vision_auto_select_if_unset` only sets the active provider when
unset. The persisted `model_per_provider` map is applied
(`attach_persistence` calls `provider.set_model` for each known
entry) — but if there's no persisted file at all, the adapter
boots with the env-var-supplied model and the map stays empty.
Verify the first-launch path: env-supplied model should flow into
the map on first persist. If not, populate the map at boot from
each adapter's `current_model()` so the persisted file always
reflects what the user is actually running. Probably already works
— worth a focused test.

### Priority 4 — Privacy posture × remote vision

Wait for a third (remote) vision adapter; cheap to land then.

### Priority 5 — Microphone consent (separate track)

Out of scope for the multimodal vision foundation; mirror the
permission tri-state when the voice/STT path lands.

## 4. Risks / things to review first

- **Vision provider id vocabulary is now triple-touched.** The
  shell ships hard-coded mappings for `ollama-vision` /
  `llamacpp-vision` in three places:
  - `apps/desktop/src/lib/mediaTurns.ts`:
    `VISION_PROVIDER_IDS`, `visionProviderShortLabel`,
    `visionRouteSummary`,
  - `apps/desktop/src/components/ActiveVisionRoute.tsx`:
    `providerShortLabel`,
  - the Rust adapter `id()` returns.
  Adding a third adapter requires updating all four. Not a hot path
  but a real coordination cost — consider extracting to a shared
  TS constant + ts-rs codegen if the vocabulary keeps growing.
- **`vision_provider.json` is now a 2-field shape.** `active` (old)
  + `model_per_provider` (new). Old files keep loading because
  `model_per_provider` has a serde default. New writers always emit
  both fields. Any future field MUST default-safe on read.
- **`MEDIA_TURN_KINDS` and the Rust `analyze_frame` outcome strings
  are dual contracts.** Adding a new media outcome requires updating
  both sides in the same change. The Vitest contract test catches
  the mismatch immediately.
- **Audit tab still has no vision provenance.** Intentional — L5's
  `AuditRecordEvent` doesn't carry L4 provider info. The History
  tab badge and body line are the right surfaces.
- **`TelemetryEntry.model` is wire-additive.** Old clients ignoring
  the field still work; the field is `skip_serializing_if = "Option::is_none"`.
- **In-flight `analyze_frame` keeps the provider AND model it
  captured.** Hot swap is per-call. The model id in telemetry is
  captured BEFORE `provider.analyze` so a concurrent
  `set_active_vision_model` can't race the recorded value.
- **Vitest pinned to ^2; jsdom pinned to ^29.** Vite 5 + Vitest 4
  are incompatible.
- **`@testing-library/react ^16` + `@testing-library/dom ^10` are
  the desktop shell's first React component-test deps.** Future
  component tests can mock `lib/api.ts` the same way `VisionBadge.test.tsx`
  does. `@testing-library/jest-dom` was deliberately NOT added —
  Vitest's matchers are sufficient. If matchers ever feel
  insufficient, evaluate jest-dom then.

## 5. Recommended next prompt (copy-paste, detailed)

Paste this into the next session as-is.

---

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state:
- `dev` is 6 commits ahead of `origin/dev` at `49d0648`.
- Push is NOT pre-authorized this session. Ask first if you think
  pushing is needed.
- All multimodal vision-track work through 2026-04-30 has shipped
  AND committed locally; nothing has been pushed.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-01_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30` to confirm the picture.
3. Read these reports for shape context:
   - `P1_VISION_BADGE_RTL_TESTS_EXECUTION_REPORT_2026-04-30.md`
   - `P2_PER_PANEL_VISION_ROUTE_HINT_EXECUTION_REPORT_2026-04-30.md`
   - `P3_TRUST_DRAWER_MODEL_ANNOTATION_EXECUTION_REPORT_2026-04-30.md`
4. Skim:
   - `apps/desktop/src-tauri/src/state.rs` (TelemetryEntry shape)
   - `apps/desktop/src-tauri/src/commands.rs` (analyze_frame +
     maybe_apply_vision)
   - `apps/desktop/src/components/Transcript.tsx` (where model
     would render)
   - `apps/desktop/src/lib/mediaTurns.ts` (the helpers triple-touched
     by adapter id additions)

Session focus (multimodal / vision assistant track ONLY):

P1 — Persona transcript meta annotation
  - Backend: extend `MessageMeta` with `model: Option<String>`. In
    `analyze_frame`, populate it from the same `vision_model`
    capture that already lands in telemetry. `submit_turn`
    finalize_turn leaves it None.
  - Frontend: TS `MessageMeta` gains `model?: string`. Surface it
    in `Transcript.tsx` where provider/tier/latency render today.
  - Tests: cargo + pnpm. Pure helper for the rendering string is
    fine if a helper is called for; otherwise inline rendering.

P2 — First-launch model persistence verification
  - Add a focused desktop-shell test that boots an AppState with
    no persisted vision_provider.json, registers a stub adapter
    whose env-supplied model is "X", auto-selects, and verifies
    the persisted model_per_provider map reflects "X" after the
    first set_active_vision_model OR after any boot-time write.
    If the map is empty by default, decide whether to seed it from
    each adapter's current_model() at boot.
  - Adjust attach_persistence / auto_select_first_if_unset as
    needed; preserve all existing tests.

P3 — Optional: AETHER_VISION_MODEL_TTL_SECS env override
  - Read in main.rs; fall back to DEFAULT_TTL when unset/malformed.
  - Tests: parse helper.

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
- Do NOT add new test deps unless the targeted task requires one
  AND it is the right scope.

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
  HANDOFF_2026-05-01_CONTINUE_COMPANION_BUILD.md: morning status,
  commits this run, reports, what the product does now, next
  priorities ordered with suggested shapes, risks, and a
  copy-paste recommended next prompt.
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
