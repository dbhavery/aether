# Handoff — Presence V1 steps 2+3, Memory V2 step 2, Quality-Eval v1.1 (2026-05-16)

**Written:** 2026-05-16 evening.
**Branch state:** `dev`, local commits ahead of `origin/dev`. Push
**not authorized** this session.
**Next session mode:** Memory V2 step 3 (per-domain write/read
plumbing using the policy surface landed this session).
Alternatives: Presence V1 step 4 (rot guard), Quality-Eval
session-log replay importer.

---

## 0. Morning status (post-session)

Full check matrix run 2026-05-16 (evening):

| Check | Result |
| --- | --- |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | 149 / 149 |
| `cargo test -p aether-l3-presence` | **22 / 22** (was 12; +10) |
| `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp --test-threads=1` | **96 / 96** |
| `cargo test -p aether-l4-router …` (parallel) | 95 / 96 — one pre-existing env flake (`from_env_uses_defaults_when_vars_unset`); not introduced by this session; passes in isolation |
| `apps/desktop/src-tauri cargo test --features …` | **175 / 175** (was 154; +21) |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | 51 anchors OK |
| `python tools/lint-voice-doc/check.py` | 48 anchors OK |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 pass |
| `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial` | **6 FAIL** (as designed) |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 227 kB / 65 kB gzip |
| `apps/desktop && pnpm test` | 145 / 145 |

Known flaky tests:
- `state::tests::yaml_persona_pack_merges_into_catalog` (pre-
  existing, AETHER_PERSONAS_DIR contamination).
- `providers::ollama::tests::from_env_uses_defaults_when_vars_unset`
  (pre-existing, same env-contamination class). Passes in
  isolation. Flagged but **not** addressed in this session —
  fixing the env-seam is a cross-cutting cleanup that would pull
  focus from the main tracks.

---

## 1. What landed this session

### Presence V1 step 2 — user-attention controller + OS idle probe + UI

- `packages/l3-presence/src/attention.rs` — new module.
  `UserAttention { Active | Idle | Away }`,
  `AttentionThresholds`, `AttentionSnapshot`, `AttentionEvent`,
  `UserAttentionController`. Pure state machine, hot-swappable,
  bounded transition log, no OS code (L3 keeps `deny(unsafe_code)`).
- `apps/desktop/src-tauri/src/idle_probe.rs` — new shell-side
  module. `IdleProbe` trait + `WindowsIdleProbe` (raw
  `GetLastInputInfo` / `GetTickCount` FFI, no new dep) +
  `UnsupportedIdleProbe` (macOS / Linux stub, honest `None`).
- `AppState.attention` + `AppState.presence_history`. Boot wires
  thresholds from `presence.json`. `set_presence_config`
  validates (10–86 400 s, `away > idle`) and hot-swaps the
  controller.
- New Tauri commands: `presence_status` (the user-attention axis;
  orthogonal to the pre-existing `presence_current` posture axis
  — both coexist), `presence_recent_history`.
- New event-bus kind: `presence:attention`. Emitted only on
  transitions; the 1 Hz poll loop is silent otherwise.
- Poll loop in `main.rs::run_presence_loop` via
  `tauri::async_runtime::spawn` + `tokio::time::interval`.

### Presence V1 step 3 — Trust drawer presence-history rendering

- Trust drawer History tab now interleaves presence rows with
  turn telemetry (sorted by timestamp). New `presence` filter
  pill. Muted visual tier. Gated by the
  `history_in_trust_drawer` Settings toggle.
- Live updates via `onAttention` subscriber.
- `coalescePresence()` suppresses A → B → A blips within 5 s so
  the History surface doesn't read as a debug log.

### Presence V1 step 2 — Settings threshold editing UI

- `ThresholdEditor` component replaces the step-1 read-only
  line. Two number inputs with inline validation. Apply button
  commits as one `setPresenceConfig` round trip. Reset snaps
  back to persisted values.

### Memory V2 step 2 — `memory.json` policy surface

- `apps/desktop/src-tauri/src/memory_config.rs` — new module
  mirroring `presence_config.rs`. `MemoryDomain` (six per design
  §1), `MemoryRisk` (Auto / Ask / Deny), `MemoryConfig`
  (retention map, risk map, embeddings block).
- `attach_memory_config_file`, `memory_config()`,
  `set_memory_config()` on `AppState`. Validation at the
  boundary: `embeddings.enabled = true` requires a named
  provider.
- New Tauri commands: `get_memory_config`, `set_memory_config`.
- Settings drawer: new Memory section with six `MemoryRiskRow`
  rows. Retention shown as a read-only hint (retention editing
  lands with the sweep slice).
- TS types, constants, and API wrappers.

### Quality-Eval v1.1 — live backend + more adversarial probes

- `tools/evals/__main__.py` — new `--backend {dry-run,ollama}`
  flag. Live Ollama hook posts the final user turn to
  `/api/generate`, captures the response. Env-controlled
  (`AETHER_EVAL_OLLAMA_{BASE_URL,MODEL,TIMEOUT_S}`). New
  `--capture-into <dir>` emits per-scenario markdown.
- Five new adversarial probes (one per remaining domain):
  tool-use, voice, memory, presence, vision. All FAIL as
  designed (detectors firing).
- `tools/evals/README.md` updated to v1.1.
- `tools/evals/baseline/2026-05-16.md` fresh baseline (6 / 6 pass).

### Execution reports

- [PRESENCE_V1_STEP2_EXECUTION_REPORT_2026-05-16.md](file:///C:/Users/dbhav/Projects/aether/PRESENCE_V1_STEP2_EXECUTION_REPORT_2026-05-16.md)
- [MEMORY_V2_STEP2_EXECUTION_REPORT_2026-05-16.md](file:///C:/Users/dbhav/Projects/aether/MEMORY_V2_STEP2_EXECUTION_REPORT_2026-05-16.md)
- [QUALITY_EVAL_V1_1_EXECUTION_REPORT_2026-05-16.md](file:///C:/Users/dbhav/Projects/aether/QUALITY_EVAL_V1_1_EXECUTION_REPORT_2026-05-16.md)

---

## 2. Track status snapshot

- **Vision V1** — DONE (maintenance only). Rot-guarded.
- **Voice V1** — DONE (steps 1–6 + real whisper.cpp inference).
  Rot-guarded.
- **Presence V1**:
  - Step 0 (architecture) ✅
  - Step 1 (presence.json + Settings toggles) ✅
  - **Step 2 (controller + OS-idle probe + events + threshold
    editing UI) ✅ this session**
  - **Step 3 (Trust drawer presence-history rendering) ✅ this
    session**
  - Step 4 (presence rot guard) — pending
- **Memory V2**:
  - Step 0 (architecture) ✅
  - Step 1 (L5 additive capabilities) ✅
  - **Step 2 (`memory.json` + policy surface + Settings
    section) ✅ this session**
  - Step 3 (per-domain write/read plumbing) — pending
  - Steps 4–7 (Memory tab, sweep, embeddings, rot guard) — pending
- **Quality-Eval**:
  - v1 scaffold ✅
  - **v1.1 (adversarial probes + live Ollama hook) ✅ this
    session**
  - Replay importer, rot guard, regression harness — pending

---

## 3. Risks / things to review first

1. **Unpushed commits.** Push not authorized this session.
2. **Poll loop not exercised in CI.** The Presence V1 step 2
   poll loop runs only inside the live Tauri app. Manual
   validation is "open the app, don't touch anything for
   `idle_after_s` seconds, watch the Trust drawer History surface
   a presence transition". The state machine has full unit
   coverage; the loop glue (spawn + sleep + tick) does not.
3. **macOS / Linux stubs are truthful but unusable.** On those
   platforms the UI shows "idle probe unavailable" and the
   controller holds at Active. Real probes are a future slice.
   Don't ship to mac/Linux users until they exist.
4. **Tick wrap-around.** `GetTickCount` wraps every ~49.7 days.
   `u32::wrapping_sub` handles it; documented in the Windows
   probe. Still, a user who never reboots for 50 days and never
   touches the mouse for the last 5 minutes could produce an
   idle reading that underflows into a small positive value
   — the only real-world effect is "one erroneous tick, then
   the next tick self-corrects". Deemed acceptable.
5. **Memory V2 step 2 has no L2 consumer yet.** The policy
   surface is landed and validated end-to-end; the memory
   kernel's write path still uses the legacy granular
   capabilities. Step 3 wires the coarse capabilities through.
6. **Quality-Eval Ollama hook untested against a live server.**
   The Python unit logic (arg parsing, prompt extraction,
   response handling) is sound; the live `/api/generate` round
   trip has not been exercised this session (no Ollama instance
   was spun up). Fastest validation is `AETHER_EVAL_OLLAMA_MODEL
   = llama3.2 python tools/evals/__main__.py --backend ollama`.
7. **Flaky L4 test.** `from_env_uses_defaults_when_vars_unset`
   joins the known-flaky list alongside the persona test. Same
   env-contamination pattern; passes in isolation. Neither is
   introduced by this session.
8. **`tokio = { features = ["time"] }` added.** Already
   transitively pulled by tauri, so net-zero build cost, but
   it's a new direct dep line in `apps/desktop/src-tauri/
   Cargo.toml`. Scope limited to `time`.

---

## 4. Decisions log (new + carried)

New this session:

- 26. **Raw FFI over `user-idle` crate.** Single call site,
  single platform. 40 lines of `extern "system"` beats a new
  dep.
- 27. **Two presence axes, two commands.** `presence_current`
  (posture) and `presence_status` (user-attention) coexist on
  separate event streams (`presence:update`,
  `presence:attention`). No rename, no alias — the turn engine
  still owns its posture contract.
- 28. **Presence history ring is shell-owned, not L3.** L3's
  ring is controller-scoped (debugging); the shell's ring is
  UX-scoped (Trust drawer).
- 29. **Tri-state Memory risk (`Auto` / `Ask` / `Deny`) reuses
  the Media permission visual language.** Keeps the Settings
  surface coherent across subsystems.
- 30. **Embeddings enable without provider is rejected at the
  policy boundary.** Catches "on but nothing wired" in the
  Settings round trip instead of letting the later embeddings
  slice fail silently.
- 31. **Quality-Eval live backend is single-turn only.** Richer
  wiring (persona compile, memory injection) belongs in L4, not
  in the eval harness.

Carried (unchanged): 1–25 from prior handoffs.

---

## 5. Remaining backlog (priority-ordered)

1. **Memory V2 step 3** — per-domain write/read plumbing.
   Route user-sensitive domains through the Ask flow using the
   policy surface landed this session.
2. **Presence V1 step 4** — presence rot guard. Seed
   `tools/lint-presence-doc/` from the anchors in
   `docs/PRESENCE-V1-ARCHITECTURE.md`, flip doc to "current".
3. **Real idle probes for macOS / Linux.** `CGEventSource…`
   (mac), `XScreenSaverQueryInfo` (Linux X11). Wayland a
   separate track.
4. **Session lifecycle presence axis.** Design §2's
   `Foreground / Background / Closed` — wire Tauri window
   focus events into a sibling controller.
5. **Memory V2 step 4** — Trust drawer Memory tab.
6. **Memory V2 step 5** — retention sweep (boot + low-rate
   background tick).
7. **Quality-Eval v1.2** — session-log replay importer.
8. **Quality-Eval v1.3** — `tools/lint-quality-doc/` rot guard
   + `pnpm eval` wrapper.
9. **Memory V2 step 6** — embeddings (opt-in, local-only).
10. **Memory V2 step 7** — memory rot guard.
11. **Cross-cutting** — migrate `AETHER_PERSONAS_DIR` +
    `AETHER_OLLAMA_*` test seams to per-test `TempDir` / scoped
    env to kill the two known flakes.

---

## 6. Next recommended prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is ahead of `origin/dev` (see `git log` for count).
- Working tree clean.
- Push is NOT pre-authorized.
- Vision V1 complete and rot-guarded.
- Voice V1 complete and rot-guarded.
- Presence V1 steps 1–3 complete: presence.json, Settings
  toggles + thresholds, user-attention controller + OS-idle
  probe (Windows-first), poll loop, presence_status +
  presence_recent_history commands, Trust drawer rendering.
  Step 4 (rot guard) pending.
- Memory V2 step 1 (L5 capabilities) and step 2 (memory.json +
  policy surface + Settings section) complete. No L2 consumer
  yet — that's step 3's job.
- Quality-Eval v1.1 complete (six seed scenarios + six
  adversarial probes + live Ollama backend hook + refreshed
  baseline). Dry-run baseline 6 / 6 pass; adversarial 6 FAIL
  as designed.

Mandatory first steps:
1. Read `HANDOFF_2026-05-16_PRESENCE_MEMORY_EVAL.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read the three 2026-05-16 execution reports referenced in
   the handoff.
4. Read `docs/MEMORY-V2-ARCHITECTURE.md` end to end — §4 (audit
   posture), §5 (telemetry kinds), and §8 (hard constraints)
   are the binding surfaces for step 3.
5. Skim:
   - `packages/l2-memory/src/kernel.rs` — where the new
     capabilities need to land.
   - `apps/desktop/src-tauri/src/memory_config.rs` — the
     policy surface that step 3 consumes.
   - `packages/l5-policy/src/engine.rs` — decision flow the
     write path is gated on.

Session focus: **Memory V2 step 3 — per-domain write/read
plumbing via the policy surface.**

Scope:
- Thread `MemoryConfig::risk_for(domain)` into the memory
  write path so user-sensitive domains (Facts, Artifacts) flip
  from `NeedsUpgrade` to the proper `Ask` flow.
- Wire `MemoryWrite` / `MemoryForget` / `MemoryEdit` capability
  emissions at the L2 kernel surface (additive — existing
  granular emissions remain until a separate simplification
  slice).
- Emit `memory_written` / `memory_forgotten` / `memory_edited`
  telemetry kinds per design §5. Audit row per write. Sampled
  audit for reads (1 per ~100 per domain per session).
- Tests: per-domain routing table, Ask-flow round trip for a
  Facts write, Auto-flow round trip for a Durable write,
  retention-sweep eviction still emits the right capability
  (even though the sweep itself is step 5).

Out of scope:
- Trust drawer Memory tab (step 4).
- Retention sweep (step 5).
- Embeddings (step 6).
- Memory rot guard (step 7).
- Presence rot guard / macOS-Linux probes (separate tracks).

Hard constraints (still in force):
- No push.
- No release / signing.
- No raw-media persistence.
- User-sensitive domains default Ask — do not flip.
- No `AuditRecordEvent` shape change.
- No new heavy dependencies.
- Do not destabilise the vision / voice / presence rot guards.
- Do not weaken the eval harness — dry-run must still be
  6 / 6 pass.
- Do not touch the two known flaky tests
  (`yaml_persona_pack_merges_into_catalog`,
  `from_env_uses_defaults_when_vars_unset`).

Process:
1. Thread `MemoryConfig` into the L2 write/read path behind a
   small trait so the kernel doesn't depend directly on the
   shell's `AppState`.
2. Audit-row + telemetry emission on each write path.
3. Sampled read audit (1/100 per domain per session).
4. TS types + UI bindings for the new telemetry kinds.
5. Tests.
6. Full check matrix (fmt, workspace, l4-router, shell, lints,
   evals, pnpm typecheck/build/test).
7. Commit in scoped slices.
8. Execution report + fresh handoff.

Stay strictly on step 3. No drift into step 4 (Memory tab) or
step 5 (retention sweep).
```
