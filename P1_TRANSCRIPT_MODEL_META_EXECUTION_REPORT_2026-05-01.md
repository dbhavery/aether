# P1 — Transcript model meta annotation — execution report (2026-05-01)

**Status:** Shipped, committed `bf06af3` on `dev`. Push not authorized.

## Goal

Surface the same vision model identifier the badge / panel hint /
Trust drawer already show, in the assistant transcript bubble, so
the user can tell *which model produced which message* at a glance
when scrolling chat history.

## Surfaces touched

### Backend

- `apps/desktop/src-tauri/src/commands.rs`:
  - `MessageMeta` grows `model: Option<String>` (skip-serialize when
    None; additive on the wire — old clients ignoring the field
    still work).
  - `analyze_frame` populates `meta.model` from the same
    `vision_model` capture that already lands in telemetry, so
    transcript and Trust drawer never diverge.
  - `finalize_turn` (text-only path) and the provider-error path
    leave it `None` — the bubble never lies about which route ran.

### Frontend

- `apps/desktop/src/lib/types.ts` — TS `MessageMeta` interface gains
  optional `model?: string`.
- `apps/desktop/src/components/Transcript.tsx`:
  - `buildMetaParts(meta)` extracted as a pure helper. Order is
    `tier · provider · model · latency · tokens`. Model chip is
    included only when `meta.model` is a non-empty (non-whitespace)
    string. Exposed as a named export so unit tests can lock the
    inclusion / ordering / formatting without rendering React.
  - `MessageMetaFooter` calls the helper and renders the chips
    space-dot-separated as before.

### Tests

- `apps/desktop/src/components/Transcript.test.tsx` (new, 5 tests):
  - empty meta → no parts
  - text-only turn → tier · provider · latency · tokens (no model)
  - vision turn → tier · provider · model · latency · tokens
  - empty / whitespace / undefined model → omitted
  - single-side token counts → fallback chip
- `apps/desktop && pnpm test`: **64 / 64** (was 59, +5).
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp`:
  **66 / 66** (no count change; existing test sites updated to set
  `model: None` for the now-additive shape).
- `pnpm typecheck && pnpm build`: clean.

## Hard-constraint compliance

- No push.
- No L5 audit semantics changes; provider/model still live in
  telemetry and now also in transcript meta — both are runtime
  metadata, not policy decisions.
- `MessageMeta` change is additive — old transcripts loaded from
  durable memory have no `model` field and render exactly as before.
- No broad refactor of the message model.
- No new providers, no streaming, no privacy posture changes.

## Risks / follow-ups

- The model chip can grow long for verbose model ids
  (`qwen2.5-vl-72b-instruct-q4_k_m`); the footer line wraps
  naturally because the chips are inline `<span>`s and the parent
  is `text-[10.5px] font-mono` not `whitespace-nowrap`.
- If a future reflex / non-vision adapter starts reporting a model,
  the chip will start appearing on its bubbles too. That's
  consistent with how the field is named and would be the right
  outcome.
