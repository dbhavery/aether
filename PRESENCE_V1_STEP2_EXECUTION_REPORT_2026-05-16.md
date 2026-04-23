# Presence V1 step 2 — user-attention controller + OS idle probe + UI — execution report (2026-05-16)

**Status:** Shipped locally on `dev`. Push not authorized.

## Goal

Land the first live user-attention axis per
`docs/PRESENCE-V1-ARCHITECTURE.md` §§2, 3, 6. Active / Idle / Away
state machine in L3, Windows-first OS idle probe in the shell,
bounded transition history, `presence_status` Tauri command,
Settings threshold editing UI. Observational — no L5 capability
gate, no audit rows.

## Surfaces touched

### `packages/l3-presence/src/attention.rs` (new)

- `UserAttention` enum (`Active` / `Idle` / `Away`) with
  `label()`.
- `AttentionThresholds` with design defaults (120 s / 600 s) and
  `sanitized()` coercion — nonsensical values (`idle_after_s = 0`,
  `away_after_s <= idle_after_s`) are coerced to a usable shape
  rather than panicking.
- `AttentionSnapshot` + `AttentionEvent` serde-ready payloads.
- `UserAttentionController`:
  - Pure state machine — no OS calls, no implicit clock. The shell
    feeds `(now_ms, idle_seconds)` each tick.
  - `tick()` returns `Some(AttentionEvent)` only on state change;
    holding steady is silent.
  - `set_thresholds` + `set_enabled` hot-swap; takes effect on the
    next tick, no restart.
  - Re-enable resets `since_ms` so a long disabled window doesn't
    instantly surface as "you've been Away".
  - `None` idle reading (macOS / Linux stubs) → stay at Active,
    flag `probe_supported = false` on the snapshot.
  - Bounded transition log (`TRANSITION_LOG_CAP = 32`).
- 12 tests covering threshold boundaries, transitions, disabled
  no-op, re-enable reset, hot-swap, unsupported probe, bounded log,
  bucket-bounce silence.

L3 keeps `#![deny(unsafe_code)]` — all OS code lives in the shell.

### `packages/l3-presence/src/lib.rs`

- Re-exports: `UserAttentionController`, `UserAttention`,
  `AttentionThresholds`, `AttentionSnapshot`, `AttentionEvent`.

### `apps/desktop/src-tauri/src/idle_probe.rs` (new)

- `IdleProbe` trait (`idle_seconds() -> Option<u64>` + `label()`).
- `WindowsIdleProbe` — raw FFI into `user32!GetLastInputInfo` +
  `kernel32!GetTickCount`. Unsafe is scoped to a single block;
  tick-wrap handled by `u32::wrapping_sub`. **No new dependency
  added** (decision logged below).
- `UnsupportedIdleProbe` — honest `None` stub for macOS / Linux.
  Future real probes land in the same file behind `#[cfg]` gates.
- `MockIdleProbe` (test-only) — scripted readings for integration
  tests.
- `platform_probe()` factory returns the right `Box<dyn IdleProbe>`
  at compile time.
- 4 tests (factory, mock, unsupported; Windows-only test when
  `cfg(windows)`).

### `apps/desktop/src-tauri/src/state.rs`

- New fields on `AppState`: `attention: Arc<UserAttentionController>`
  and `presence_history: Mutex<VecDeque<PresenceHistoryEntry>>`.
- New capacity constant `PRESENCE_HISTORY_CAPACITY = 64`.
- New `PresenceHistoryEntry` row type: `{ kind, from, to,
  idle_seconds, at_ms }`. `kind = "presence_state_changed"` per
  design §5; step-3 additions (`session_opened` etc.) share the
  same shape.
- `attach_presence_config_file` now propagates thresholds +
  enabled flag into the live controller on boot.
- `set_presence_config` rejects out-of-range values (10–86 400 s
  inclusive), rejects `away ≤ idle`, and hot-swaps the controller
  on success.
- New helpers: `attention_tick`, `attention_snapshot`,
  `push_presence_history`, `presence_history_recent`.
- 5 new state-level tests locking: threshold range rejection,
  ordering rejection, hot-swap propagation, disabled no-op,
  bounded ring.

### `apps/desktop/src-tauri/src/commands.rs`

- New `PresenceStatusPayload` (state, since_ms, idle_seconds,
  enabled, probe_supported, idle_after_s, away_after_s).
- `presence_status` Tauri command — orthogonal to the pre-existing
  `presence_current`; the old command continues to return the
  posture (Quiet / Listening / …) axis. **No rename, no alias.**
- `presence_recent_history` Tauri command (newest-first, default
  limit 50) — consumed by the Trust drawer.
- `AttentionEventPayload` + `drive_attention_tick(app, state,
  now_ms, idle_seconds)` helper called from the poll loop.

### `apps/desktop/src-tauri/src/main.rs`

- New `PRESENCE_POLL_MS = 1_000` constant (1 Hz — the design doc
  suggested 2 Hz; 1 Hz is conservative given thresholds resolve
  in seconds, and a GetLastInputInfo call is effectively free).
- `run_presence_loop(app)` async task spawned from the Tauri
  setup hook via `tauri::async_runtime::spawn`. Uses
  `tokio::time::interval` with `MissedTickBehavior::Skip` so
  hibernation / sleep doesn't cause a burst of backlogged ticks.
- Registers new Tauri commands: `presence_status`,
  `presence_recent_history`.

### `apps/desktop/src-tauri/Cargo.toml`

- Added `tokio = { version = "1", features = ["time"] }` — already
  transitively pulled by tauri, declared explicitly so the
  `tokio::time::interval` call in `run_presence_loop` resolves.
  Feature scope is `time` only — no runtime, no IO, no networking.

### `apps/desktop/src/lib/types.ts` + `api.ts`

- New types: `UserAttentionLabel`, `PresenceStatusPayload`,
  `PresenceHistoryEntry`, `AttentionEventPayload`.
- New constants: `PRESENCE_THRESHOLD_MIN_S = 10`,
  `PRESENCE_THRESHOLD_MAX_S = 86_400`.
- New API wrappers: `presenceStatus`, `presenceRecentHistory`,
  `onAttention` (event-bus subscriber for `presence:attention`).

### `apps/desktop/src/components/SettingsDrawer.tsx`

- Replaced the step-1 read-only threshold line with a new
  `ThresholdEditor` component:
  - Two `<input type="number">` controls for `idle_after_s` and
    `away_after_s`, bounds mirrored client-side.
  - Inline validation: positive integer, 10–86 400, `away > idle`.
  - Apply button commits as a single `setPresenceConfig` round
    trip; Reset snaps inputs back to the persisted values.
  - Existing `enabled` + `history_in_trust_drawer` toggles
    unchanged.

### `apps/desktop/src/components/TrustDrawer.tsx` (Presence V1 step 3)

- History tab now interleaves turn telemetry with presence
  transitions, sorted by timestamp descending.
- New `presence` filter pill alongside `all` / `media only` /
  `voice only`.
- `PresenceHistoryRow` — muted visual tier (`text-aether-dim` +
  softer border) so presence doesn't drown turn rows.
- Live updates via `onAttention` event-bus subscriber — new
  transitions push to the top of the list without re-fetching.
- Gated by the `history_in_trust_drawer` toggle: when off, rows
  are suppressed and an inline note points at Settings.
- `coalescePresence()` collapses A → B → A sequences within 5 s —
  avoids one-second blips (mouse touch in Idle state) polluting
  the History surface.

## Checks — all green

- `cargo fmt --all -- --check` — clean
- `cargo check --workspace` — clean
- `cargo test --workspace` — 149 / 149
- `cargo test -p aether-l3-presence` — **22 / 22** (was 12; +10)
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp --test-threads=1`
  — **96 / 96**
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp`
  — 95 / 96 (one pre-existing env-contamination flake under
  parallel execution — `from_env_uses_defaults_when_vars_unset`;
  not introduced by this session; passes in isolation)
- `apps/desktop/src-tauri cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp`
  — **175 / 175** (was 154; +21 from new idle-probe + attention-
  wiring + memory-config tests)
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — 51 anchors
- `python tools/lint-voice-doc/check.py` — 48 anchors
- `python tools/evals/__main__.py --dry-run` — 6 / 6 pass
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` —
  145 / 145, build 227 kB gzipped 65 kB

## Hard-constraint compliance

- **No push.** ✅
- **No L5 capability gate for presence.** ✅ Design §4.
- **No L5 audit rows.** ✅ Transitions go to a shell-owned ring
  buffer, not `AuditRecordEvent`.
- **No continuous capture / wake words / VAD.** ✅ Presence reads
  OS idle only.
- **No new heavy dependencies.** ✅ Chose raw FFI over the
  `user-idle` crate (decision below). `tokio = { features =
  ["time"] }` declared explicitly but was already transitively
  pulled by tauri — net-zero runtime change.
- **No destabilisation of vision / voice rot guards.** ✅ Both
  still pass with their pre-existing anchor counts.
- **No weakening of the eval harness.** ✅ Baseline still 6 / 6.
- **Additive-only config evolution.** ✅ `presence.json` shape
  unchanged; existing fields + tests survive.
- **Platform parity honest.** ✅ macOS / Linux stubs return `None`
  and the snapshot flags `probe_supported = false` — the UI
  surfaces this truthfully rather than pretending to know.

## Design decisions worth noting

1. **Raw FFI over `user-idle` crate.** Single call site, single
   platform that needs real code today, no auth / cross-platform
   state to wrap. 40 lines of `extern "system"` + one unsafe
   block beats a new dependency. macOS / Linux land under the
   same trait when their probes ship. Documented loudly in
   `idle_probe.rs`.
2. **Presence axis kept orthogonal to posture axis.** New command
   `presence_status` + new `presence:attention` event. The
   pre-existing `presence_current` / `presence:update` surface is
   untouched — the turn engine still owns its posture axis and
   nothing else in the codebase has to change.
3. **Bounded `presence_history` is shell-owned, not L3.** L3's
   bounded transition log is controller-scoped. The shell's
   history ring is UX-scoped (renders in the Trust drawer) and
   does not need to live in the domain crate.
4. **Hot-swap semantics.** `set_presence_config` both persists
   AND propagates thresholds + enabled flag into the live
   controller. No restart required. Locked by the
   `set_presence_config_hot_swaps_attention_thresholds_and_enabled`
   test.
5. **Disable reset.** Re-enabling after a disabled window zeroes
   the controller state and `since_ms`, so the very next tick
   starts classifying from a clean baseline instead of treating
   accumulated idle time as if presence had been watching.
6. **Threshold validation at the boundary.** 10–86 400 s hard
   bounds enforced by Rust and mirrored client-side. Rejecting
   a 5-second Away threshold keeps the Settings UI honest even
   if someone hand-edits `presence.json`.
7. **Event coalescing on the UI side.** A → B → A within 5 s
   collapses; the backend still records every transition (useful
   for debugging). Keeps Trust drawer from reading like a debug
   log.

## Known limitations / future work

- **macOS / Linux idle probes not shipped.** Stub returns `None`;
  UI surfaces `probe_supported = false`. Implementing
  `XScreenSaverQueryInfo` (Linux/X11) and
  `CGEventSourceSecondsSinceLastEventType` (macOS) is a follow-up
  slice. Neither has Wayland coverage today.
- **No rot guard yet.** `tools/lint-presence-doc/` is step 4 in the
  design doc's sequencing. When it lands, the doc flips from
  "design-only" to "current".
- **Session lifecycle axis not implemented.** Design §2 mentions
  `Session` (`Foreground` / `Background` / `Closed`); v1 covers
  the user-attention axis only. Follow-up slice can wire Tauri
  window focus events into a sibling controller.
- **Poll rate hardcoded.** Moved into `main.rs` as a constant;
  future work could make it configurable via `presence.json`.
