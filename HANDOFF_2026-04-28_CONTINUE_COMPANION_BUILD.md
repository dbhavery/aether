# Handoff — Continue the companion build (2026-04-28)

**Written:** 2026-04-26 (autonomous continuation run).
**Branch state:** `dev`, **18** commits ahead of origin/dev, **NOT pushed**.
**Push authorization:** still NOT granted.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track.

---

## 0. Morning status

1. Branch `dev` has three new feat commits + this handoff/report
   batch on top of `5506755`:
   - `4ae9a13` feat(l4): second vision provider — llama.cpp HTTP adapter
   - `6257bd5` feat(apps/desktop): vision provider registry + runtime swap
   - `3f19678` feat(apps/desktop): per-panel cue history for camera + screen
2. Working tree clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp`
     → **45 / 45** (was 35; +10 llamacpp)
   - `apps/desktop/src-tauri && cargo test`
     → **48 / 48** default, **54 / 54** with both provider features
     (was 37 / 43; +11 registry)
   - `python tools/lint-layer-boundaries/check.py` → 0 violations
   - `apps/desktop && pnpm typecheck && pnpm build` → clean
4. **Not pushed.**

## 1. Commits landed this run

```
4ae9a13 feat(l4): second vision provider — llama.cpp HTTP adapter
6257bd5 feat(apps/desktop): vision provider registry + runtime swap
3f19678 feat(apps/desktop): per-panel cue history for camera + screen
(this handoff commit)
```

## 2. Execution reports

- [P1_SECOND_VISION_PROVIDER_EXECUTION_REPORT_2026-04-26.md](file:///C:/Users/dbhav/Projects/aether/P1_SECOND_VISION_PROVIDER_EXECUTION_REPORT_2026-04-26.md)
- [P2_VISION_RUNTIME_SWAP_EXECUTION_REPORT_2026-04-26.md](file:///C:/Users/dbhav/Projects/aether/P2_VISION_RUNTIME_SWAP_EXECUTION_REPORT_2026-04-26.md)
- [P3_CUE_HISTORY_EXECUTION_REPORT_2026-04-26.md](file:///C:/Users/dbhav/Projects/aether/P3_CUE_HISTORY_EXECUTION_REPORT_2026-04-26.md)

## 3. What the product does now

Everything from yesterday, plus:

- **Two vision providers.** `OllamaVisionProvider` (Ollama `/api/chat`
  + `images`) and `LlamaCppVisionProvider` (llama-server
  `/v1/chat/completions` + OpenAI `image_url` content blocks). Each
  feature-gated independently; both can be enabled together.
- **Runtime vision swap.** A registry on `AppState` holds zero or
  more providers + an active selection. New Tauri commands
  `list_vision_providers` and `set_active_vision_provider`. Selection
  persists at `<app_data>/vision_provider.json`. The VisionBadge in
  the camera/screen panels exposes a dropdown so users can hot-swap
  without restarting.
- **Per-panel cue history.** Camera and Screen panels each remember
  the last 5 cues that produced a `frame_analyzed` outcome. Click a
  chip to repopulate the input; edit before submitting. Stored under
  `localStorage["aether.cue-history.camera"]` and the screen
  equivalent. Never enters durable memory.

## 4. What to build next — multimodal track only

> No vision-track follow-up was attempted as P4 cleanup since the
> three priorities consumed the run. The list below is the
> remaining horizon, ordered.

### Priority 1 — Vitest harness + cue-history unit tests

The cue-history layer is pure (`applyCue`) but not yet covered by
unit tests because the repo has no Vitest setup. Land Vitest, port
the dedup/cap/empty-input/ordering invariants into a test file, and
also cover `MEDIA_TURN_KINDS` / `isMediaTurn` from `TrustDrawer.tsx`
while you're there.

### Priority 2 — Per-provider model discovery in the dropdown

The dropdown lists registered providers, not the models each daemon
has. Adding a per-provider "list models" call (Ollama exposes
`/api/tags`; llama-server exposes `/v1/models`) and surfacing the
result inline would let the user pick a model without restarting.

### Priority 3 — Privacy-posture interaction

Today both vision adapters are local-first by env, so privacy
posture has nothing to gate. When a remote vision adapter lands
(third provider — Anthropic / OpenAI / Gemini), `Strict` posture
must refuse remote vision calls. Wire the gate now so the third
provider lands cheaply.

### Priority 4 — Vision in the Trust drawer

The Trust drawer's Audit tab shows L5 audit rows; History tab shows
telemetry. Add a small per-row "vision provider" annotation when a
turn used vision, sourced from the existing telemetry `provider`
field (already set to `"ollama-vision"` / `"llamacpp-vision"`).
Pure UI work.

### Priority 5 — Microphone consent (separate track)

Out of scope for this multimodal vision foundation. Mirror the
permission-tri-state model when the voice/STT path lands.

## 5. Risks / things to review first

- **`vision_provider.json` is a contract.** Once shipped, the
  `{"active": "..."}` shape must be additive. A third provider
  whose id changes between releases will silently fall back to the
  first-registered provider, which is the correct safety behaviour
  but worth flagging in release notes.
- **Two vision adapters share `ureq`.** Both adapters opt into the
  same `dep:ureq` via their respective features. Enabling
  `vision-llamacpp` without `ollama-provider` still pulls `ureq`
  in — expected.
- **`LlamaCppConfigError` mirrors `OllamaConfigError`** but is a
  separate type. Don't try to unify them across the feature
  boundary; the duplication is intentional so each adapter compiles
  independently.
- **Cue history saves only on `frame_analyzed`.** Permission
  refusals (`permission_denied`, `permission_ask`) and policy blocks
  do NOT enter history. If you want refused cues to surface for
  retry, add a separate "drafts" surface — don't change the
  history-save predicate.
- **Hot-swap is per-call, not per-turn.** Swapping the active
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
1. Read HANDOFF_2026-04-28_CONTINUE_COMPANION_BUILD.md.
2. Run `git status` and `git log --oneline -30`.
3. Read P1/P2/P3 execution reports from 2026-04-26.

Session focus (multimodal/video assistant track ONLY):
- P1: land Vitest harness + unit tests for cue history
      (apps/desktop/src/lib/cueHistory.ts: applyCue invariants)
      AND for MEDIA_TURN_KINDS / isMediaTurn (TrustDrawer.tsx).
- P2: per-provider model discovery — list models the active
      vision daemon has, surface in the VisionBadge dropdown.
      Ollama: /api/tags. llama.cpp: /v1/models. Keep failures
      silent with a graceful "models unavailable" message.
- P3: vision-provider annotation in Trust drawer (Audit + History
      tabs) sourced from the telemetry provider field.

Rules:
- No push, no release, no weakening tests or boundary rules.
- No streaming / continuous capture modes.
- No mic / voice work.
- Do not unify LlamaCppConfigError + OllamaConfigError across
  the feature boundary.

Before stopping:
- keep git status clean,
- commit with clear scoped messages,
- update execution reports and the handoff with what changed,
  what remains, and a copy-paste next prompt.
```
