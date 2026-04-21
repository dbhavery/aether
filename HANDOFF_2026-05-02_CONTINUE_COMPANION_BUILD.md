# Handoff — Continue the companion build (2026-05-02)

**Written:** 2026-05-01 (autonomous continuation run).
**Branch state:** `dev`, **10 commits ahead of origin/dev** at SHA `f5ecb24`.
**Push status:** **NOT authorized this session.** All 10 commits
since the last push are local. Treat the next push as a fresh
authorization decision.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track only.

---

## 0. Morning status

1. `dev` is 10 commits ahead of `origin/dev` at `f5ecb24`.
2. Working tree clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`
     → **77 / 77** (was 66; +5 first-launch seeding, +6 TTL env)
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
   - `apps/desktop && pnpm test` → **64 / 64** (was 59; +5 transcript
     buildMetaParts)

## 1. What landed in the most recent run

| SHA | Subject |
| --- | --- |
| `bf06af3` | feat(apps/desktop): annotate transcript bubbles with vision model |
| `521d30f` | feat(apps/desktop): seed first-launch vision model_per_provider from adapters |
| `f5ecb24` | feat(apps/desktop): AETHER_VISION_MODEL_TTL_SECS env override for cache |

Reports:

- [P1_TRANSCRIPT_MODEL_META_EXECUTION_REPORT_2026-05-01.md](file:///C:/Users/dbhav/Projects/aether/P1_TRANSCRIPT_MODEL_META_EXECUTION_REPORT_2026-05-01.md)
- [P2_FIRST_LAUNCH_MODEL_PERSISTENCE_EXECUTION_REPORT_2026-05-01.md](file:///C:/Users/dbhav/Projects/aether/P2_FIRST_LAUNCH_MODEL_PERSISTENCE_EXECUTION_REPORT_2026-05-01.md)
- [P3_VISION_CACHE_TTL_ENV_OVERRIDE_EXECUTION_REPORT_2026-05-01.md](file:///C:/Users/dbhav/Projects/aether/P3_VISION_CACHE_TTL_ENV_OVERRIDE_EXECUTION_REPORT_2026-05-01.md)

## 2. Multimodal product surface today

End-to-end story, ground up:

1. **Local-only media permissions.** `MediaPermissions { camera,
   screen }` tri-state persisted at
   `<app_data>/media_permissions.json`.
2. **Camera + Screen capture surfaces.** Single-shot,
   getUserMedia/getDisplayMedia, OS picker for screen, default OFF.
3. **`analyze_frame` Tauri command.** Permission gate → policy
   audit → memory → presence → telemetry.
4. **Vision provider registry.** Ollama and llama.cpp adapters,
   active selection persisted at
   `<app_data>/vision_provider.json`.
5. **Per-provider model selection.** `VisionProvider::set_model` /
   `current_model`. Per-provider model persisted under
   `vision_provider.json::model_per_provider`. Provider swap
   restores each provider's last pick.
6. **First-launch model seeding (NEW, P2 of 2026-05-01).** On boot,
   any registered adapter not already in `model_per_provider` gets
   seeded from its `current_model()` (the env-supplied default).
   Idempotent on later boots; persisted file always reflects the
   running configuration.
7. **Cached model lists with env override (NEW, P3 of 2026-05-01).**
   Per-provider TTL cache (default 60 s). New
   `AETHER_VISION_MODEL_TTL_SECS` env var overrides the TTL within
   `[5, 3600]`; out-of-range / non-numeric values fall back to
   default with a tracing::warn. Hot reload not supported. Manual
   `↻` refresh in the badge bypasses cache.
8. **VisionBadge UI.** Provider dropdown + clickable model chips +
   `↻` refresh + RTL component tests.
9. **Per-panel ActiveVisionRoute hint.** "→ provider · model" line
   above the Analyze button on both panels. Stays in sync with the
   badge via `onRouteChanged`.
10. **Trust drawer.** History tab shows "<provider> · <model>"
    badge + "<persona> · <provider> · <model>" body line for media
    turns. Audit tab unchanged.
11. **Transcript bubbles (NEW, P1 of 2026-05-01).** Assistant
    message footer chips now read
    `tier · provider · model · latency · tokens` for vision turns,
    and `tier · provider · latency · tokens` for text-only turns —
    consistent with the badge / hint / Trust drawer.
12. **Telemetry.** `TelemetryEntry.model: Option<String>` populated
    via the same `vision_model` capture. `MessageMeta.model` now
    mirrors it. L5 audit contract still policy-only.

## 3. What to build next — multimodal track

### Priority 1 — Bounded `MessageMeta.tier` rendering

The `tier` chip in the transcript footer carries the long vision
provider label
(`"Ollama vision · llava:latest · http://127.0.0.1:11434"`) for
vision turns. Now that the model chip exists, the tier chip is
mostly noise on those bubbles. Options:

- truncate / shorten tier to the first segment (`"Ollama vision"`)
  for vision turns — match what `ActiveVisionRoute` does;
- or drop tier entirely when the provider id is a known vision id;
- or keep tier as-is and trust the user to read the chips.

**Suggested shape** Add `formatTierForFooter(meta)` that returns the
short label for vision providers and the raw tier otherwise. Keep
the helper pure so it can be unit-tested. Deferred from this
session; one decision needed before implementation.

### Priority 2 — Provider id vocabulary deduplication

`VISION_PROVIDER_IDS` / `visionProviderShortLabel` /
`visionRouteSummary` (mediaTurns.ts) and `providerShortLabel`
(ActiveVisionRoute.tsx) hard-code `ollama-vision` /
`llamacpp-vision` in four places. Adding a third adapter needs
all four updated in lockstep. Consider extracting to a single
shared TS object — or, more aggressively, generate it from the Rust
ids via `ts-rs`. The latter is the right long-term answer; the
former is a one-session cleanup.

### Priority 3 — Cache TTL log line on boot

`ModelListCache::from_env` emits a `tracing::info` only when the env
var is set to a valid value. On default-TTL boots there's no log
line, so operators can't tell the cache is even active. Tiny:
unconditionally log "vision model-list cache TTL: Ns" at boot.

### Priority 4 — Privacy posture × remote vision

Wait for a third (remote) vision adapter; cheap to land then.

### Priority 5 — Microphone consent (separate track)

Out of scope for the multimodal vision foundation; mirror the
permission tri-state when the voice/STT path lands.

## 4. Risks / things to review first

- **Triple-touched adapter id vocabulary** (see P2 above).
  Mitigated for now by tests that span both sides; unblocked but
  growing technical debt.
- **`vision_provider.json` is a stable 2-field shape.** `active` +
  `model_per_provider`. Old files without the map keep loading via
  serde default; new writers always emit both. Any future field
  must default-safe on read.
- **`model_per_provider` is now auto-populated on first boot.** A
  user who manually deletes an entry will see it re-seeded on next
  boot. Document the contract: text-only mode = `active: null`, not
  empty map.
- **`AETHER_VISION_MODEL_TTL_SECS` is hot-reload-free.** Changing
  it requires a full app restart. Documented in the env var const.
- **Bounds `[5, 3600]`** are conservative. A power user wanting a
  24 h TTL is blocked today. Easy to widen if requested.
- **`MessageMeta.model` and `TelemetryEntry.model` come from the
  same `vision_model` capture in `maybe_apply_vision`.** The capture
  happens BEFORE `provider.analyze` so a concurrent
  `set_active_vision_model` cannot race the recorded value.
- **Vitest pinned to ^2; jsdom pinned to ^29.** Vite 5 + Vitest 4
  are incompatible.
- **`@testing-library/react ^16` + `@testing-library/dom ^10`** are
  the desktop shell's only React component-test deps.

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
- `dev` is 10 commits ahead of `origin/dev` at `f5ecb24`.
- Push is NOT pre-authorized this session. Ask first if you think
  pushing is needed.
- All multimodal vision-track work through 2026-05-01 has shipped
  AND committed locally; nothing has been pushed.

Mandatory first steps (do these in order before editing):
1. Read `HANDOFF_2026-05-02_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read these reports for shape context:
   - `P1_TRANSCRIPT_MODEL_META_EXECUTION_REPORT_2026-05-01.md`
   - `P2_FIRST_LAUNCH_MODEL_PERSISTENCE_EXECUTION_REPORT_2026-05-01.md`
   - `P3_VISION_CACHE_TTL_ENV_OVERRIDE_EXECUTION_REPORT_2026-05-01.md`
4. Skim:
   - `apps/desktop/src/components/Transcript.tsx` (footer pipeline)
   - `apps/desktop/src/lib/mediaTurns.ts` (provider id helpers)
   - `apps/desktop/src/components/ActiveVisionRoute.tsx`
     (parallel provider id helper)
   - `apps/desktop/src-tauri/src/vision_cache.rs` (TTL log gap)

Session focus (multimodal / vision assistant track ONLY):

P1 — Bounded tier rendering for vision turns
  - Decide: shorten tier in the transcript footer for vision
    providers (drop the long "Ollama vision · model · base_url"
    label down to just "Ollama vision"), OR drop tier entirely when
    the provider id is a known vision id. Lean toward "shorten to
    short label" — keeps the chip but stops it duplicating model.
  - Add a pure helper in mediaTurns.ts (or Transcript.tsx) that
    decides the displayed tier. Unit test the mapping.
  - Wire into buildMetaParts.

P2 — Provider id vocabulary deduplication
  - Extract a single shared TS source-of-truth for the two known
    vision provider ids and their short labels. Touch:
    - mediaTurns.ts (VISION_PROVIDER_IDS,
      visionProviderShortLabel, visionRouteSummary)
    - ActiveVisionRoute.tsx (providerShortLabel)
  - Either co-locate in one helper module, or generate from Rust
    via ts-rs (heavier — only land if Don wants the codegen story).
  - Tests must keep passing without changes (the helpers are pure).

P3 — Cache TTL boot log line
  - Always log "vision model-list cache TTL: Ns" at boot, not only
    on env override. Move the info log out of from_env's match arms.

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
- Do NOT introduce new vision providers in this session.
- Do NOT add new test deps (RTL is the last addition).

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
  HANDOFF_2026-05-02_CONTINUE_COMPANION_BUILD.md.
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
