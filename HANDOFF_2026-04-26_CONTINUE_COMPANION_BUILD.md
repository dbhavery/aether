# Handoff — Continue the companion build (2026-04-26)

**Written:** 2026-04-25 (autonomous continuation run).
**Branch state:** `dev`, three new commits this run, **NOT pushed**.
**Next session mode:** broad autonomous build authorization on the
multimodal/video assistant track; no push authorization assumed.

---

## 0. Morning status

1. Branch `dev` has three new local commits on top of `39e2e16`:
   - `8b5385f` feat(apps/desktop): [P1+P3 backend] media permission model + analyze_frame command
   - `76a0cb7` feat(apps/desktop): [P1 frontend] Settings drawer with media permission controls
   - `d660229` feat(apps/desktop): [P2+P3] camera capture panel + single-frame analysis UI
2. Working tree is clean.
3. Full check set is green:
   - `cargo fmt --all -- --check`
   - `cargo check --workspace`
   - `cargo test --workspace`
   - `cargo test -p aether-l2-memory --features sqlite-backend`
   - `cargo test -p aether-l6-persona`
   - `apps/desktop/src-tauri && cargo test` (37/37; was 24)
   - `python tools/lint-layer-boundaries/check.py` (0 violations)
   - `apps/desktop && pnpm typecheck && pnpm build` (clean)
4. **Not pushed.** Push authorization must be explicit.

## 1. Commits landed this run

```
8b5385f feat(apps/desktop): [P1+P3 backend] media permission model + analyze_frame command
76a0cb7 feat(apps/desktop): [P1 frontend] Settings drawer with media permission controls
d660229 feat(apps/desktop): [P2+P3] camera capture panel + single-frame analysis UI
```

## 2. Execution reports

- [P1_MEDIA_PERMISSIONS_EXECUTION_REPORT_2026-04-25.md](file:///C:/Users/dbhav/Projects/aether/P1_MEDIA_PERMISSIONS_EXECUTION_REPORT_2026-04-25.md)
- [P2_CAMERA_CAPTURE_EXECUTION_REPORT_2026-04-25.md](file:///C:/Users/dbhav/Projects/aether/P2_CAMERA_CAPTURE_EXECUTION_REPORT_2026-04-25.md)
- [P3_FRAME_ANALYSIS_EXECUTION_REPORT_2026-04-25.md](file:///C:/Users/dbhav/Projects/aether/P3_FRAME_ANALYSIS_EXECUTION_REPORT_2026-04-25.md)
- New doc: [docs/MEDIA-PERMISSIONS.md](file:///C:/Users/dbhav/Projects/aether/docs/MEDIA-PERMISSIONS.md)

## 3. What the product does now

Everything from 2026-04-25, plus:

- **Local-only media permission model.** Camera + screen each carry
  Allow/Ask/Deny tri-state. Persisted at
  `<app_data>/media_permissions.json` (atomic write-to-temp-then-rename).
  Default = both `Ask`. A new Settings button in the header opens a
  drawer with tri-state radio controls per device.
- **Camera capture surface.** A new "Camera" header button opens a
  right-side panel that wraps `MediaDevices.getUserMedia` behind
  start/stop/sample-frame controls. Permission gate runs first; the
  camera is OFF by default and only acquired on explicit Start. Live
  preview with red-dot ON/OFF indicator. Tracks released on Stop /
  Close / unmount.
- **Single-frame analysis path.** "Analyze current frame" captures a
  JPEG data URL and POSTs to a new `analyze_frame` Tauri command.
  The command enforces the permission gate, validates the data URL,
  records the request as a user-role memory entry tagged
  `[frame analysis · camera] <cue>`, dispatches through the existing
  TurnEngine, and lands an audit row + telemetry entry like any
  other turn. The transcript message returned is appended to the
  main conversation view.

## 4. What to build next — multimodal track only

### Priority 1 — Vision-capable provider behind `analyze_frame`

The current path validates the data URL and discards it server-side
because the active provider stack is text-only. Wire a vision-aware
provider (Ollama vision-tuned model, or a `LLAMA-CPP` route) so the
data URL actually reaches the model and the assistant response
reflects the frame contents. Suggested approach:
- Extend `aether-l4-router` with an optional `analyze_image` path or
  add a second route that accepts a data URL alongside the text
  utterance.
- Wire `analyze_frame` to call the new path when the active
  provider declares vision support; fall back to the current
  text-only behaviour otherwise so the abstraction stays shippable.

### Priority 2 — `MediaAnalyze` capability

`analyze_frame` currently reuses `Capability::FilesRead`. Add a
dedicated `MediaAnalyze` (or `MediaInspect`) capability in
`packages/l5-policy` so:
- the audit log distinguishes frame turns from filesystem reads,
- personas can declare a per-capability default that is independent
  of file access,
- the autonomy presets can toggle frame analysis on/off without
  affecting file reads.

### Priority 3 — Screen-capture path (P4 from this run, deferred)

The permission model already carries a `screen` field with no
consumer. Add a "Screen" button or section that captures a single
screenshot via `getDisplayMedia` (browser side; later Rust-side via
DXGI / X11) and routes it through `analyze_frame`. Same permission
gate, same audit story.

### Priority 4 — Tauri capability allowlist hardening

The Tauri `tauri.conf.json` capabilities currently allow the IPC
command surface. Audit whether `getUserMedia` / `getDisplayMedia`
need a Tauri-side capability declaration; today the webview is
permissive but a stricter policy will be needed for distribution.

### Priority 5 — Telemetry filter UI

Frame turns now share the History tab with text turns. A filter
toggle ("show frame turns only") would help reviewers audit how
often Aether looked at media.

### Priority 6 — Microphone consent (separate track)

Out of scope for the multimodal foundation, but parallel: mic
capture has its own consent path through the voice/STT track. When
that lands, mirror the model used here.

## 5. Risks / things to review first

- **`Deny` is the "Never" semantic.** Users see "Never" in the UI;
  the wire / persistence shape is `deny`. If you ever surface the
  wire shape to end users (e.g. CLI flag), use the same word.
- **`analyze_frame` reuses `FilesRead`.** Audit rows will read
  "files read" until P1 above lands. Confusing in the audit drawer
  if users start using the camera surface heavily before then.
- **`set_media_permission` parameter is `state_value` on the wire.**
  Renamed to avoid colliding with Tauri's `State<T>` extractor.
  Documented in `apps/desktop/src/lib/api.ts`. Update any future
  TypeScript bindings codegen to preserve this.
- **Camera UI uses webview MediaDevices.** Tauri 2's webview is the
  acquirer; native v4l2 / DXGI capture would land under a separate
  Rust-side capture module. Both should consult the same
  `evaluate_media_permission` gate.
- **No streaming, no continuous loop.** Every frame is a single
  explicit user-initiated POST. If you ever wire a "watch" mode,
  start a new doctrine pass — observability + audit costs change
  significantly.
- **The data URL is base64 JPEG (~90KB at 640x480).** That is fine
  for a single round-trip but you do NOT want to put data URLs
  into durable memory. The user-role memory entry deliberately
  stores the cue text only.

## 6. Recommended next prompt (copy-paste)

```
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

First:
1. Read the latest HANDOFF_2026-04-26_CONTINUE_COMPANION_BUILD.md.
2. Run `git status` and `git log --oneline -30`.
3. Read the most recent execution report(s) for the current top priority.

Session focus (multimodal/video assistant track ONLY):
- P1: vision-capable provider behind analyze_frame (Ollama
      vision-tuned model OR llama.cpp vision route).
- P2: dedicated MediaAnalyze capability in packages/l5-policy so
      frame turns carry their own audit / preset story.
- P3: screen-capture path (getDisplayMedia + analyze_frame),
      reusing the existing permission gate.

Rules:
- No push, no release, no weakening tests or boundary rules.
- No broad media permission shortcuts; reuse the existing tri-state
  gate per device.
- If blocked on P1, move to P2 (capability), then P3 (screen).
- Do not start unrelated features or refactors.

Before stopping:
- keep git status clean if possible,
- commit with clear scoped messages,
- update execution reports and the handoff with what you did, what
  remains, and an explicit next prompt focused on this same
  multimodal foundation track.
```
