# Handoff — Continue the companion build (2026-04-29)

**Written:** 2026-04-27 (autonomous continuation run).
**Branch state:** `dev`, **23** commits ahead of origin/dev.
**Push authorization:** still NOT granted.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track only.

---

## 0. Morning status

1. Branch `dev` has three new feat commits + this handoff/report
   batch on top of `2a7f955`:
   - `bd51e65` test(apps/desktop): vitest harness + cue history & media-turn tests
   - `e50a8f1` feat(l4,apps/desktop): per-provider model discovery in vision dropdown
   - `fd400c2` feat(apps/desktop): vision-provider annotation in Trust drawer History
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
   - `apps/desktop && pnpm test` → **41 / 41**
4. **Not pushed.**

## 1. Commits landed this run

```
bd51e65 test(apps/desktop): vitest harness + cue history & media-turn tests
e50a8f1 feat(l4,apps/desktop): per-provider model discovery in vision dropdown
fd400c2 feat(apps/desktop): vision-provider annotation in Trust drawer History
(this handoff commit)
```

## 2. Execution reports

- [P1_VITEST_HARNESS_EXECUTION_REPORT_2026-04-27.md](file:///C:/Users/dbhav/Projects/aether/P1_VITEST_HARNESS_EXECUTION_REPORT_2026-04-27.md)
- [P2_MODEL_DISCOVERY_EXECUTION_REPORT_2026-04-27.md](file:///C:/Users/dbhav/Projects/aether/P2_MODEL_DISCOVERY_EXECUTION_REPORT_2026-04-27.md)
- [P3_TRUST_VISION_ANNOTATION_EXECUTION_REPORT_2026-04-27.md](file:///C:/Users/dbhav/Projects/aether/P3_TRUST_VISION_ANNOTATION_EXECUTION_REPORT_2026-04-27.md)

## 3. What the product does now

Everything from yesterday, plus:

- **A frontend test harness exists.** `pnpm test` runs Vitest with
  jsdom; 41 unit tests cover the cue-history layer (18) and the
  media-turn classification + vision-provider helpers (23).
- **The vision dropdown surfaces models.** Selecting a vision
  provider triggers a `/api/tags` (Ollama) or `/v1/models`
  (llama.cpp) probe; the result renders as a row of pill chips
  under the dropdown. Failures collapse to "Models unavailable for
  this provider" — no modal noise.
- **History tab badges vision-served turns.** Telemetry rows
  produced by `OllamaVisionProvider` or `LlamaCppVisionProvider`
  carry a small green "Ollama vision" / "llama.cpp vision" pill so
  reviewers can see at a glance that the response actually came
  from a vision-capable model. Audit tab unchanged (see report
  for the contract-preservation rationale).

## 4. What to build next — multimodal track only

### Priority 1 — In-provider model selection

The dropdown shows what's available; selecting a specific model on
a provider is the natural next step. Likely shape: extend the
`VisionProvider` trait with a `set_model(id: &str)` method that
mutates the adapter's config under interior mutability, and a Tauri
command `set_active_vision_model(id)` that calls it on the active
provider only. Persist the selection alongside `vision_provider.json`.

### Priority 2 — Model availability cache invalidation

`list_vision_models` re-fetches every time the active provider
changes. A short-lived in-shell cache (e.g. 60 s TTL) plus a manual
refresh button on the model strip would smooth the UX without
chasing stale data.

### Priority 3 — Component-level tests for VisionBadge

The pure layers (`cueHistory`, `mediaTurns`) are now covered. The
next candidate is a small component test for `VisionBadge`'s
state machine (loading → models / error). Would require
`@testing-library/react` — a deliberate scope decision before
landing.

### Priority 4 — Privacy posture × remote vision

Still pending. Lands cheap when a third (remote) vision adapter
arrives.

### Priority 5 — Microphone consent (separate track)

Out of scope for this multimodal vision foundation. Mirror the
permission tri-state when the voice/STT path lands.

## 5. Risks / things to review first

- **Audit tab still has no vision provenance.** Intentional — the
  L5 audit record does not carry L4 provider info, and extending
  it would muddy the policy-vs-implementation boundary. History
  carries the badge instead. If you want the Audit tab to know,
  pick path (1) — extend `AuditRecordEvent` to attach the L4
  provider id at decision time — and accept that contract change
  in a deliberate slice.
- **`MEDIA_TURN_KINDS` and `VISION_PROVIDER_IDS` are dual contracts**
  with the Rust `analyze_frame` outcomes and the Rust
  `VisionProvider::id()` returns respectively. Adding a new media
  outcome or a new vision adapter requires updating both sides in
  the same change. Tests will catch the mismatch immediately.
- **Vitest is pinned to ^2.** Vite 5 + Vitest 4 are incompatible;
  bumping Vitest requires bumping Vite first.
- **Models endpoints are also healthcheck endpoints (Ollama).**
  Hitting `/api/tags` for both healthcheck and model listing on
  every active-provider change is fine (cheap), but worth caching
  if Don ever runs against a remote daemon.
- **Per-call hot swap semantics unchanged.** Switching the active
  provider takes effect on the next `analyze_frame`. An in-flight
  call uses whichever provider it captured at handle time.

## 6. Recommended next prompt (copy-paste)

```
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

First:
1. Read HANDOFF_2026-04-29_CONTINUE_COMPANION_BUILD.md.
2. Run `git status` and `git log --oneline -30`.
3. Read P1/P2/P3 execution reports from 2026-04-27.

Session focus (multimodal/video assistant track ONLY):
- P1: in-provider model selection. Extend the VisionProvider trait
      with set_model(id), wire a Tauri command + dropdown selection
      hooked off the existing model list. Persist the choice
      alongside vision_provider.json. Hot-swap semantics same as
      provider swap (per-call).
- P2: short-lived model-list cache (e.g. 60 s TTL) + manual
      refresh button on the model strip.
- P3: optional only if time — small component test for
      VisionBadge's state machine using @testing-library/react.

Rules:
- No push, no release, no weakening tests or boundary rules.
- No streaming / continuous capture modes.
- No mic / voice work.
- Do not unify LlamaCppConfigError + OllamaConfigError across
  the feature boundary.
- Do not extend L5's AuditRecordEvent to carry provider info
  unless explicitly required by the targeted tasks.

Before stopping:
- keep git status clean,
- commit with clear scoped messages,
- update execution reports and the handoff with what changed,
  what remains, and a copy-paste next prompt.
```
