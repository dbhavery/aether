# Handoff — Continue the companion build (2026-04-22)

**Written:** 2026-04-21 (day autonomous run, Don away).
**Branch state:** `dev`, **23 new commits** local across three runs,
**not pushed**, working tree clean.
**Next session mode:** broad autonomous build authorization, zero
launch/distribution authorization (unchanged from prior handoffs).

---

## 0. Morning status — read before touching anything

1. **Nothing has been pushed.** `git log origin/dev..dev` shows 23
   local commits: 8 from 2026-04-19 overnight, 8 from the 2026-04-20
   day run (7 feat + 1 handoff), and 7 new commits today (6 feat/test
   + this handoff once committed).
2. **Every morning-smoke gate is green.** Full check set:
   `cargo fmt --all -- --check`, `cargo check --workspace`,
   `cargo test --workspace`, tauri default + `ollama-provider`,
   `pnpm typecheck`, `pnpm build`, layer-boundary linter — all pass.
3. **Product state update vs yesterday's handoff:**
   - Assistant transcript bubbles now show a meta footer with
     **latency + token counts** when an Ollama turn reports them.
   - A **first-run autonomy-preset picker** (Observer / Assistant /
     Operator) fires after the welcome disclosure, writes the choice
     to localStorage.
   - **Typed provider errors** surface as in-transcript system
     messages with actionable copy (`ollama serve`, `ollama pull foo`,
     `AETHER_OLLAMA_TIMEOUT_MS`) instead of raw Tauri errors.
   - **Ember** joins the persona catalog (Formal / Balanced /
     Cautious / Dry). Three personas now.
   - **Last-picked persona persists across launches** via
     localStorage; `AETHER_PERSONA` env var still wins.
   - **Two Ask/Approve cycle tests** now guard the shell's engine
     path directly against `AppState`.
4. **Legacy `desktop/` (Python) and `frontend/` (Next.js v1) are
   still untouched.** CLAUDE.md §2 additive-by-default rule honoured.

## 1. Commits added in this day run (newest first)

```
b19c4f6 test(apps/desktop): [P7] Ask->Approve/Reject cycle tests against AppState
1fb1ad7 feat(apps/desktop): [P5,P6] third persona Ember + persona persistence
c93be4d feat(apps/desktop): [P4] typed provider errors surface as transcript system messages
5b4348d feat(apps/desktop): [P6] onboarding autonomy-preset picker
f5bfda2 feat(l1,l4,apps/desktop): [P2d] latency + token telemetry in RouteOutcome and UI
```

(Plus `docs(handoff): 2026-04-22 continuation handoff` once this file
is committed.)

## 2. Per-slice execution reports in this run

- [P2D_LATENCY_TOKEN_TELEMETRY_EXECUTION_REPORT_2026-04-21.md](file:///C:/Users/dbhav/Projects/aether/P2D_LATENCY_TOKEN_TELEMETRY_EXECUTION_REPORT_2026-04-21.md)
- [P6_ONBOARDING_PRESET_PICKER_EXECUTION_REPORT_2026-04-21.md](file:///C:/Users/dbhav/Projects/aether/P6_ONBOARDING_PRESET_PICKER_EXECUTION_REPORT_2026-04-21.md)
- [P4_TYPED_PROVIDER_ERROR_UI_EXECUTION_REPORT_2026-04-21.md](file:///C:/Users/dbhav/Projects/aether/P4_TYPED_PROVIDER_ERROR_UI_EXECUTION_REPORT_2026-04-21.md)
- [P5_P6_EMBER_AND_PERSONA_PERSISTENCE_EXECUTION_REPORT_2026-04-21.md](file:///C:/Users/dbhav/Projects/aether/P5_P6_EMBER_AND_PERSONA_PERSISTENCE_EXECUTION_REPORT_2026-04-21.md)
- [P7_ASK_APPROVE_CYCLE_TEST_EXECUTION_REPORT_2026-04-21.md](file:///C:/Users/dbhav/Projects/aether/P7_ASK_APPROVE_CYCLE_TEST_EXECUTION_REPORT_2026-04-21.md)

## 3. What the product does now

Everything from the 2026-04-21 handoff, plus:

- Each Ollama-tier assistant reply carries `latency_ms` and (when
  reported) `prompt_tokens` + `completion_tokens`. The transcript
  meta-footer renders `tier · provider · 1.4s · p42/c17 tok`.
- First-launch flow: welcome disclosure → autonomy preset picker
  (with Can / Asks / Never detail per preset) → chat. Both steps are
  skippable; preset-picker persists an "I'll decide later" sentinel
  so it doesn't re-prompt.
- Provider failures (daemon down, model missing, timeout, bad body)
  appear inside the transcript as a system-role message with
  actionable copy, instead of as a raw red-error blob.
- Persona catalog: Aurora (Warm / Balanced) · Sable (Neutral / Bold)
  · Ember (Formal / Cautious). Cautious stance flows through
  `EngineConfig::with_persona_overlay` to tighten Auto/Ask/Deny.
- Persona choice persists across launches. `AETHER_PERSONA` env
  still overrides.

## 4. What to build next — priority backlog for the next unattended run

Ordered by visible-product payoff. Tackle top-down; de-scope if one
blocks.

### Priority 1 — P3: Durable memory (deferred from today)

`SqliteSessionMemoryStore` behind a `sqlite-backend` cargo feature on
`aether-l2-memory`, with a new migration
`packages/storage/migrations/0004_conversation_log.sql`. Default
build stays in-memory; durable mode opts in via feature flag + a
builder mirroring `DurableBackends::open(path)` in L5.

Scope (tight):
- `packages/storage/migrations/0004_conversation_log.sql` with
  `conversation_log(session_id TEXT, sequence INTEGER, role TEXT,
  content TEXT, timestamp_ms INTEGER)` + index on
  `(session_id, sequence)`.
- New module `packages/l2-memory/src/sqlite_session.rs` implementing
  `SessionMemoryStore`.
- Behind `#[cfg(feature = "sqlite-backend")]` in `lib.rs`.
- 3-4 integration tests in `packages/l2-memory/tests/`:
  `append_survives_reopen`, `recent_returns_per_session`,
  `clear_session_leaves_other_sessions_intact`, append-only behaviour
  over reopen.

This is the foundation for "what do you remember about me?" UX and
for surfacing the meta-footer's latency/token data in a long-term
analytics view.

### Priority 2 — Wire preset picker into policy

The autonomy preset picker stores a user choice but does not yet
modify policy. Add `EngineConfig::with_preset_overlay(preset)` that
adjusts capability defaults per preset (Observer = read-only,
Assistant = current defaults, Operator = auto-approve read + ask
write). Shell sends the stored preset on boot / switch_persona.

### Priority 3 — Plumb preset into tauri-plugin-store (or native command)

Today the preset lives in `window.localStorage`. Once the backend
needs to read it (Priority 2), consolidate onto either
`tauri-plugin-store` (adds a dep) or a pair of native Tauri commands
`get_onboarding_state` / `set_onboarding_state` writing JSON under
`app_config_dir`. Second option keeps the dep surface flat.

### Priority 4 — Persona-switch banner in transcript

When the persona is switched mid-session, the transcript currently
wipes silently. Emit a system message (`"Switched to Ember ·
session reset"`) so users see the state change and understand why
earlier context vanished. Small, two-file change.

### Priority 5 — Trust drawer: surface latency/token history

Trust drawer already lists audit rows. Add a secondary tab or footer
section showing per-turn latency + token counts for the last N
Ollama turns, now that `RouteOutcome` carries them. Pulls from L2
memory + a fresh per-turn trace we'd write as part of P3.

### Priority 6 — Persona-pack YAML loader

Replace `state.rs::default_catalog()` with a loader that reads
`personas/*.yaml`. Unblocks contributors adding personas without
modifying Rust. Depends on `planning/17_persona_pack_schema.md`.

### Priority 7 — Wave-5 work opens up

Once durable memory lands and preset wiring is in, the next
horizon is **tool execution through L5** (Wave 5+). Nothing to
plan precisely until we're closer.

## 5. Risks / things to review first in the morning

- **P3 is still open and is the single biggest product unlock left.**
  Today's run deliberately stopped short to avoid a half-built
  migration. Do P3 first on the next run.
- **localStorage is doing a lot of work.** Three keys now:
  disclosure-ack, autonomy-preset, last-persona. Consolidating onto
  a single Tauri-side store is worth doing before adding a fourth.
- **`EngineConfig::wave3_default` still governs policy on boot.** The
  autonomy-preset choice is visible to the user but invisible to the
  engine. Wiring through is Priority 2.
- **MemoryAwareRouter::build_prompt is still dead on the Ollama path**
  (role-tagged messages win there) but alive for the reflex stub.
  Don't prune yet; a second provider without chat-template support
  would fall back onto it.
- **No regression guard on the persona-switch memory wipe.** If we
  decide that's wrong behaviour (Priority 4 argues the UX is wrong,
  not the wipe), the test in `AppState::switch_persona` needs to
  change accordingly.

## 6. How to run / validate

```bash
# From repo root (Windows bash)
export PATH="$HOME/.cargo/bin:$PATH"
cargo fmt --all -- --check
cargo check --workspace
cargo test --workspace
python tools/lint-layer-boundaries/check.py

cd apps/desktop/src-tauri
cargo check
cargo check --features ollama-provider
cargo test                            # 13 tests
cargo test --features ollama-provider # 19 tests

cd ../..
cd apps/desktop
pnpm typecheck
pnpm build
pnpm tauri dev                        # launches the real shell

# Exercise the new preset picker:
#   — clear localStorage, relaunch, step through welcome + preset.

# Exercise Ember:
AETHER_PERSONA=ember pnpm tauri dev

# Exercise Ollama with latency/token meta footer:
ollama serve
ollama pull gemma3
export AETHER_OLLAMA_MODEL=gemma3
pnpm tauri dev -- --features ollama-provider
```

---

## 7. Copy-paste starting prompt for the next unattended session

```
You are Claude Code, working on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch:    dev (23 new commits local only, not pushed)

Tonight's mission continues three prior unattended runs that scaffolded
the Tauri desktop shell and landed progressive-enhancement slices on
top. Don is away — broad autonomous build authorization, zero
launch/distribution authorization.

Read in this exact order before touching anything:

1. HANDOFF_2026-04-22_CONTINUE_COMPANION_BUILD.md
2. HANDOFF_2026-04-21_CONTINUE_COMPANION_BUILD.md (prior context)
3. HANDOFF_2026-04-20_CONTINUE_COMPANION_BUILD.md (even prior)
4. apps/desktop/README.md
5. packages/storage/migrations/0003_audit_seal.sql (pattern for
   0004 you'll write tonight)
6. packages/l5-policy/src/sqlite_* (pattern for
   SqliteSessionMemoryStore you'll write tonight)
7. tools/lint-layer-boundaries/check.py
8. git status + git log --oneline -20

---

### Autonomy authorization

This is a long autonomous multi-hour build run. Don has said:

- Maximum productive build autonomy, zero launch/distribution
  autonomy.
- Build aggressively; don't ask routine questions.
- Make reasonable product / engineering decisions.
- If one task blocks, de-scope and continue to the next valuable
  slice.

You ARE authorized to:
- expand the desktop shell, engine layers, and supporting crates,
- add tests, reports, docs, handoffs,
- create multiple local commits,
- refactor implementation details where helpful,
- mark legacy areas as deprecated if useful.

You are NOT authorized to:
- push anything,
- publish a release,
- touch signing / notarization / release secrets,
- weaken tests, lint, CI, or boundary rules,
- do destructive cleanup of legacy trees.

Do not stop after the first completed task. Keep chaining slices.
Leave the repo in a reviewable state by morning.

---

### Priority backlog for this run

Work through these in order. Commit cleanly between slices.

P1 — Durable memory. New sqlite-backend feature on aether-l2-memory,
      SqliteSessionMemoryStore implementing the existing
      SessionMemoryStore trait. Migration 0004_conversation_log.sql
      in packages/storage/migrations/. Pattern-match on
      packages/l5-policy's sqlite_grant_ledger.rs /
      sqlite_audit_store.rs. Default build stays in-memory.

P2 — Wire autonomy preset into policy. EngineConfig::
      with_preset_overlay that adjusts capability defaults per
      preset. Shell sends the stored preset on boot/switch_persona.

P3 — Consolidate onboarding persistence. Either introduce
      tauri-plugin-store or a native get_onboarding_state /
      set_onboarding_state command pair. Currently localStorage.

P4 — Emit a system message when a persona switch wipes the session
      so the user sees "Switched to Ember · session reset"
      instead of a silent clear.

P5 — Trust drawer gains a latency/tokens history tab or footer for
      recent Ollama turns. Pulls from a telemetry hook written
      during P1.

P6 — Persona-pack YAML loader (optional — may be a dedicated run).

---

### Work cadence (unchanged)

Per completed slice:
1. Implement.
2. Run focused tests first.
3. Run full check set:
   - cargo fmt --all -- --check
   - cargo check --workspace
   - cargo test --workspace
   - cd apps/desktop && pnpm typecheck && pnpm build
   - cd apps/desktop/src-tauri && cargo check [ + --features ollama-provider]
   - python tools/lint-layer-boundaries/check.py
4. Don't weaken a check to keep moving.
5. Write a per-slice execution report at repo root.
6. Commit with a scoped, conventional message ending with
   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
7. Next slice.

---

### End-of-run deliverables

Before stopping:
1. Clean git status.
2. Per-slice reports.
3. HANDOFF_2026-04-23_CONTINUE_COMPANION_BUILD.md with completed
   work, commit list, updated backlog, risks, and a copy-paste
   starting prompt.

Governing principle: Maximum productive build autonomy, zero
launch/distribution autonomy.

Start by reading the files listed above, confirming git state, then
executing P1 (durable memory).
```

---

Good luck in the morning.
