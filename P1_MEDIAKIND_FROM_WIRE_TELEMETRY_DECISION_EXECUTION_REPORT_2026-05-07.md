# P1 — `MediaKind::from_wire` Err path telemetry — decision report (2026-05-07)

**Status:** Decision locked. No code change.
**Branch:** `dev`. Push not authorized for this session.

## Question

When `MediaKind::from_wire(&request.kind)` returns `None` inside
`analyze_frame` (apps/desktop/src-tauri/src/commands.rs:1142), the
call short-circuits with a hard string error (`"unknown media kind:
{kind}"`) **without** recording a telemetry entry. This is the only
early-exit of `analyze_frame` that does not appear in the Trust
drawer's History tab.

2026-05-06's early-exit telemetry round (commit `d61a97e`) left this
branch alone deliberately and flagged it as an open question in
[HANDOFF_2026-05-07_CONTINUE_COMPANION_BUILD.md](file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-07_CONTINUE_COMPANION_BUILD.md)
P1.

Two options:

- **(a) Record a `frame_invalid_kind` telemetry entry** — consistent
  with the other three early-exit paths (`frame_invalid`,
  `permission_denied`, `permission_ask`). History tab would render
  every failure mode.
- **(b) Keep the hard error, no telemetry** — document that the
  History tab is scoped to user-attempted analyses, not internal IPC
  contract violations.

## Decision: (b) — no telemetry. Keep the hard error.

## Rationale

### 1. Different audience

The existing three early-exit kinds all reflect **user actions**:
the user clicked Analyze, the system evaluated the request, and it
was rejected for a user-facing reason (permission gate or malformed
capture). The History tab is the user's trust ledger — "what did I
do, what did the system decide?"

`MediaKind::from_wire` failing reflects an **IPC contract
violation** — the frontend sent a `kind` value that is neither
`"camera"` nor `"screen"`. That is a code bug, not a user condition.
Surfacing it in History would conflate two distinct severities in a
single ledger.

### 2. No user-controlled path to malformed `kind`

`analyze_frame`'s `kind` originates from two hard-coded frontend call
sites — `CameraPanel` (camera) and `ScreenPanel` (screen). There is
no user-controlled, free-form path that can produce a third value.
The only way `from_wire` can fail in production is:

- a type drift between frontend and shell that TS typecheck missed,
- a maliciously-crafted IPC call (not a threat surface we're
  modelling in v1),
- or a refactor bug.

All three are code bugs. Code bugs should be loud, not silently
recorded for later inspection.

### 3. The hard error is already loud

Today the `?` operator on line 1143 returns the error string
verbatim to the caller. The UI surfaces it as a toast/inline error.
A developer or user hitting the condition sees "unknown media kind:
foo" immediately — louder than a silent History row that most users
never open.

### 4. Contract minimalism

Every kind added to `MEDIA_TURN_KINDS`
(`apps/desktop/src/lib/mediaTurns.ts`) is a widening of the
telemetry contract. Once added, removing it is a breaking change for
any future TS consumer that switches exhaustively on the kind union.
The 2026-05-06 round added `frame_invalid` deliberately; adding
`frame_invalid_kind` for a "shouldn't happen" path would widen the
vocabulary without proportional user value.

This mirrors the restraint locked for `vision_provider.json`:
additive changes are cheap to ship but not free, and every one
compounds the future-maintenance surface.

### 5. Symmetry with `maybe_apply_vision`

`maybe_apply_vision` mirrors the `validate_frame_data_url` guard but
logs at **debug, not WARN**, because the shell-side gate already
owned the case. The same principle applies here: the hard error
path in `analyze_frame` already owns the contract-violation case;
adding telemetry would be a second, redundant surface for a bug that
will be caught in QA or at the TS boundary.

## What DOES warrant a future revisit

If any of these happen, reopen the question:

- a remote vision adapter lands and expands the valid `kind`
  vocabulary (e.g. `"upload"`, `"paste"`), making the space
  user-controllable,
- TS loses the exhaustive typecheck on the `kind` field (e.g. a
  generic `string` escapes from somewhere),
- a real bug ever ships that sends a malformed `kind` in production,
  confirming the case is user-reachable.

Until then, `frame_invalid_kind` remains intentionally absent.

## Surfaces touched

- `docs/VISION-V1-ARCHITECTURE.md` §6: new paragraph noting the
  `MediaKind::from_wire` Err path and why it does not emit
  telemetry. The five-kind contract is preserved.

## No code change

- `apps/desktop/src-tauri/src/commands.rs::analyze_frame` —
  unchanged.
- `apps/desktop/src/lib/mediaTurns.ts::MEDIA_TURN_KINDS` —
  unchanged.
- `apps/desktop/src/components/TrustDrawer.tsx::kindClass` —
  unchanged.

## Tests

Docs-only change. Full check set run for hygiene:

- `cargo fmt --all -- --check` — clean
- `cargo check --workspace` — clean
- `cargo test --workspace` — green
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` — 57 / 57
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` — 93 / 93
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — 86 / 86

## Hard-constraint compliance

- No push without explicit authorization.
- No new providers.
- No mic / voice / streaming work.
- No L5 audit contract changes.
- No `vision_provider.json` contract changes.
- No new test deps.
- `AuditRecordEvent` untouched.
- Durable-memory image posture untouched.
