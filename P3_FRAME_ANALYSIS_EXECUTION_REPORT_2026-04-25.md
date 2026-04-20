# P3 — Single-frame analysis path (2026-04-25)

## Goal

Wire the camera-capture surface to the active turn engine via a new
`analyze_frame` Tauri command, so a captured frame becomes a normal
audited turn — same memory, same telemetry, same persona overlay,
gated by the P1 permission model.

## What shipped

### Rust — `apps/desktop/src-tauri/src/commands.rs`

- `AnalyzeFrameRequest { kind, frame_data_url, note? }` — the request
  envelope. `kind` selects which media-permission gate must be open
  (`camera` | `screen`); `frame_data_url` is a `data:image/...;base64,...`
  blob; `note` is an optional human cue.
- `FrameAnalysisOutcome { turn_id, kind, message, error_note }` —
  mirrors `TurnOutcomePayload` so the UI can re-use the same
  rendering helpers. `kind ∈ {"frame_analyzed", "frame_blocked",
  "permission_denied", "permission_ask"}`.
- `analyze_frame` command — the foundation hook for video assistant
  work:
  1. Enforces the media permission gate. `Deny` short-circuits with
     a friendly "disabled in Settings" system message; `Ask` returns
     a hint that the UI should flip the stored posture before
     retrying. Neither branch invokes the model.
  2. Validates the data URL prefix (`data:image/...`) so a malformed
     payload never reaches the model layer.
  3. Records the request as a user-role memory entry tagged with
     `[frame analysis · camera] <cue>` so transcript review reads
     coherently.
  4. Builds a `TurnRequest` with `Capability::FilesRead` /
     `ResourceScope::None` and dispatches through the active
     `TurnEngine`. Frame analysis is not a side channel — it goes
     through L5/L6 like every other turn.
  5. Records telemetry with `kind="frame_analyzed"` so the Trust
     drawer's History tab can surface how often Aether looked at
     media.
- Presence transitions to `Thinking` with a per-kind detail string
  during the call and back to `Quiet` afterward, matching the
  conventions of `submit_turn`.

### Rust — `apps/desktop/src-tauri/src/main.rs`

- Command registered in `invoke_handler`.

### Frontend — `apps/desktop/src/lib/types.ts`, `api.ts`

- `FrameAnalysisKind`, `FrameAnalysisOutcome` types mirrored.
- `AnalyzeFrameRequest` interface + `analyzeFrame(req)` typed
  wrapper.

### Frontend — `apps/desktop/src/components/CameraPanel.tsx`

- "Analyze current frame" button captures the latest video frame to
  a JPEG data URL (`image/jpeg`, quality 0.82), bundles it with the
  optional note, and posts to `analyzeFrame`. Returned transcript
  messages are forwarded to `App.tsx`'s `onFrameAnalyzed` handler so
  they land in the main conversation view.

## Trust + audit

- Frame turns flow through the existing policy engine, so every call
  produces an audit row in L5 — visible in the Trust drawer's Audit
  tab.
- Telemetry rows carry `kind="frame_analyzed"` for UX clarity in the
  History tab.

## What this slice deliberately does NOT do

- **No vision-model wire-up.** The local provider stack is text-only
  today; the foundation is the path, not the modality. The
  data URL is validated and discarded server-side. When a vision
  provider lands, the same command can pass `frame_data_url` straight
  through.
- **No streaming.** Every frame is a single explicit user-initiated
  request.
- **No new capability.** Reused `Capability::FilesRead` (read-only
  observation, no filesystem touch). A dedicated `MediaAnalyze`
  capability is a natural follow-up once the policy schema is
  opened.

## Verification

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` / `cargo test --workspace` — clean.
- `apps/desktop/src-tauri && cargo test` — 37 passed.
- `python tools/lint-layer-boundaries/check.py` — 0 violations.
- `apps/desktop && pnpm typecheck && pnpm build` — clean.

## Notes for review

- The `state_value` parameter name on `set_media_permission` is to
  avoid the IPC parameter colliding with Tauri's `State<T>`
  extractor. Documented in `api.ts`.
- The user-role memory entry uses a short `[frame analysis · …]`
  prefix instead of stuffing the data URL into the transcript —
  the URL would be useless noise on review and would bloat the
  database.
- Future capability split: when `MediaAnalyze` lands, swap the
  `Capability::FilesRead` constant in `analyze_frame` and the same
  approval/audit story flows through the Trust drawer with no other
  shell changes.
