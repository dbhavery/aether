# Tauri Desktop Shell v0 — Execution Report

**Date:** 2026-04-19 (night session, unattended build run)
**Branch:** `dev` (local only, not pushed)
**Commits added tonight:** 8 (see HANDOFF doc).

---

## 1. Status

**Complete.** Aether has a runnable desktop shell. It wraps the existing
Rust engine path end-to-end — no logic in the webview, no second
implementation.

What a user sees on launch (after `pnpm install && pnpm tauri dev`):

- A one-time local-first **disclosure modal** (plain-language privacy
  statement, dismissible, re-accessible from the **About** button).
- A **persona card** introducing "Aurora" with her compiled tier
  (`local-full`) and output mode (`balanced`).
- A **header** with a live presence dot (quiet / listening / thinking /
  awaiting-approval / responding), provider badge, and Memory / Trust /
  New session / About controls.
- A **chat transcript** with user / assistant / system message styles;
  assistant messages carry a `tier · provider` meta-footer.
- An **input bar** with Enter-to-send, Shift+Enter newline, Ctrl+K focus.
- An **approval modal** for L5 Ask decisions: capability · scope ·
  reason · ticket id, with clear Approve-once / Decline buttons and a
  short explanation of what "decline" means.
- A **memory drawer** showing the session's transcript ring.
- A **trust drawer** showing every sealed L5 audit row this session —
  first real audit-centre surface.

Ollama provider integration still lives behind `--features ollama-provider`
and the `AETHER_OLLAMA_*` env vars. The shell falls back silently to
the reflex stub if the daemon is unreachable; the provider badge tells
the user which mode is active.

## 2. What shipped

### 2.1 Rust backend — standalone Cargo workspace at `apps/desktop/src-tauri/`

Intentionally out of the root workspace so the Tauri dep graph doesn't
slow down `cargo check --workspace`. The boundary linter only
regulates `packages/l*-*`, so `apps/desktop/src-tauri` is invisible to
it.

| File | Purpose |
|---|---|
| `src/main.rs` | Tauri builder, plugins, command registration |
| `src/state.rs` | `AppState` owning engine, policy, memory, presence, audit, pending-approval registry |
| `src/commands.rs` | 7 typed commands, 1 event channel |
| `src/adapter.rs` | L4→L1 adapter + `ReflexModelRouter` (mirrors `apps/l1-cli`) |
| `src/memory_router.rs` | L2-aware `TurnRouter` wrapper (mirrors `apps/l1-cli`) |
| `src/provider.rs` | `ProviderMode` enum + tier translation |
| `capabilities/default.json` | Default-deny allowlist (core:default + window + event + app only) |
| `tauri.conf.json` | Single main window, strict CSP, `bundle.active = false` |
| `icons/icon.{png,ico,svg}` | Placeholder "Ae" glyph generated with Pillow |

**Commands:**

```
companion_banner() -> CompanionBanner
submit_turn(text: String) -> TurnOutcomePayload
resolve_approval(ticket_id: String, approve: bool) -> TurnOutcomePayload
presence_current() -> PresencePayload
memory_recent() -> Vec<TranscriptMessage>
clear_session() -> ()
audit_recent(limit: Option<u32>) -> Vec<TrustAuditRow>
```

**Events:** `presence:update` (emitted on every presence transition).

**Plugins used:**

- `tauri-plugin-single-instance` — prevents two instances racing state.
- `tauri-plugin-window-state` — remembers window layout.

**Plugins deliberately NOT used:** `fs`, `shell`, `http`,
`notification`, `autostart`, `dialog`. When those become needed, each
widening must pass through an L5 grant path per
`planning/plans/X3_tauri_architecture.md` §5–§7.

### 2.2 Frontend — React 18 + Vite 5 + TypeScript + Tailwind 3 at `apps/desktop/src/`

| File | Purpose |
|---|---|
| `App.tsx` | Root composition, presence subscription, drawer state |
| `lib/api.ts` | Typed `invoke()` / `listen()` wrapper (the only file that imports `@tauri-apps/api`) |
| `lib/types.ts` | Payload types mirroring the Rust command surface |
| `components/Header.tsx` | Persona name, presence dot, provider badge, action buttons |
| `components/PresenceDot.tsx` | 5-state coloured pulse dot |
| `components/ProviderBadge.tsx` | Model/provider mode indicator |
| `components/PersonaCard.tsx` | First-screen identity card |
| `components/Disclosure.tsx` | One-time local-first privacy banner |
| `components/Transcript.tsx` | Chat log with user/assistant/system styles + tier·provider footer |
| `components/InputBar.tsx` | Textarea, keyboard shortcuts, send button |
| `components/ApprovalModal.tsx` | L7.1 approval UI with clear capability/scope/reason |
| `components/MemoryDrawer.tsx` | Session transcript ring inspector |
| `components/TrustDrawer.tsx` | Audit log viewer (allowed/asked/denied colouring) |

**Aesthetic:** deep 3D neumorphic monochrome per
`planning/05_ux_principles.md`. Tokens in `tailwind.config.ts` are
bound to `packages/ui-kit/src/tokens.ts`. Warm-grey accent
(`#c9c9d1`) — no indigo/purple AI slop.

### 2.3 Build wiring

- `pnpm-workspace.yaml` adds `apps/desktop`.
- `apps/desktop/package.json` pulls `@tauri-apps/cli` locally so no
  global install is required.
- `apps/desktop/.gitignore` excludes `node_modules`, `dist`,
  `src-tauri/target`, `src-tauri/gen`, `src-tauri/Cargo.lock`.

## 3. Checks run

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` (root) | clean |
| `cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check` | clean |
| `cargo check --workspace` (root) | clean (no regressions) |
| `cargo check` (src-tauri, default) | clean |
| `cargo check --features ollama-provider` (src-tauri) | clean |
| `cargo test --workspace` | all green, 0 FAILED |
| `pnpm typecheck` (apps/desktop) | clean |
| `pnpm build` (apps/desktop) | clean — 163 KB JS gzipped to 51 KB |
| `python tools/lint-layer-boundaries/check.py` | `OK (0 violations)` |

## 4. Design decisions worth reviewing

- **React + Vite + Tailwind 3** chosen over Solid/vanilla for
  alignment with doctrine (`X3_tauri_architecture.md` §4 names
  React/TS) and to leave a sensible shell-adapter path open for
  reusing primitives later.
- **Standalone Cargo workspace** for `apps/desktop/src-tauri/` — the
  Tauri dep graph is ~300 crates; keeping it nested would slow every
  root-workspace build.
- **Two-call approval flow** (`submit_turn` → pending registry →
  `resolve_approval`) instead of a tokio channel held inside a
  command. Simpler, stateless across calls, and aligns with the
  frontend's natural turn/approval state machine.
- **`ProviderMode` enum + visible provider label** — respects the
  doctrine that local vs remote is a deliberate, inspectable choice.
- **Warm-grey accent** — avoiding the indigo/purple AI default that
  `planning/05_ux_principles.md` explicitly rejects. Easy to tune in
  one file if Don prefers something different.
- **Disclosure copy is my draft** — plain, short, honest about
  current limitations. Worth a read-through before any public
  demo.
- **Pillow-generated icon** — placeholder "Ae" glyph. Real icon work
  belongs to the brand pass.

## 5. Known gaps

- Not launched by me — I wrote and compiled the code but did not run
  `pnpm tauri dev` tonight (would require interactive WebView2 check
  and a live window). Don should do that as first thing in morning.
- `tauri.conf.json` uses `icons/icon.png` (Pillow-generated). Fine for
  dev; replace for any bundled build.
- No Tauri E2E tests. The Rust engine path is covered by
  `apps/l1-cli` tests; the new command surface is currently only type-
  checked.
- Memory drawer uses a refresh key rather than a `memory:update`
  event channel. Reactive updates would be a small follow-up.
- Approval modal has basic focus management but no focus trap.
- Presence events fire only on explicit `set_state` calls; if a UI
  later wants "keep-alive" signals or idle timers, that's additive.

## 6. Handoff

See `HANDOFF_2026-04-20_CONTINUE_COMPANION_BUILD.md` for what remains
and the copy-paste starting prompt for the next unattended session.
