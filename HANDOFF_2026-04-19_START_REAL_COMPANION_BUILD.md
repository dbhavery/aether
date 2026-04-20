# Handoff — Start Real Companion Build

**Date written:** 2026-04-19 (end of OSS Preview 0 push)
**Branch state at handoff:** `dev` at `e7d2461`, pushed to `origin/dev`; tag `v0.1.0-oss-preview.0` at `e27cb0c` published as GitHub prerelease.
**Working tree:** clean.

---

## 0. Read this first

The scaffolding phase is over. OSS Preview 0 is live with doctrine, workspace, L5 durable + sealed audit, L1 turn FSM, L6 persona compiler, and a working L1↔L4↔L6 CLI demo. What's been shipped is architecture and engine scaffolding. What comes next is **making Aether behave like a companion.**

The next several sessions should collectively move from *"it routes decisions through L5 correctly"* to *"Don can sit down, talk to it, and it feels like a real local-first assistant."* No LLM calls yet — we still build deterministic, testable slices — but the loop closes end-to-end.

**Mandatory before editing anything:**

1. `git status` — confirm clean. `git log --oneline -20` — confirm you're at `e7d2461` or newer.
2. Read the current vision doctrine: `planning/00_VISION_AND_GUARDRAILS.md`, `planning/01_product_doctrine.md`.
3. Read the most recent execution reports to understand what exists vs what's deferred:
   - `L6_2_EXECUTION_REPORT_2026-04-19.md` (most recent)
   - `WAVE4_6_EXECUTION_REPORT_2026-04-19.md` (audit sealing)
   - `L1_1_EXECUTION_REPORT_2026-04-19.md` (turn FSM)
   - `OSS_PREVIEW_RELEASE_1_REPORT_2026-04-19.md` (what's publicly shipped)
4. Run the demo once to see the current end-to-end path:
   ```bash
   cargo run -p aether-l1-cli
   ```
   Expected: persona banner ("Aurora", tier `local-full`, Balanced mode) + full L6 system prompt + FSM traces for each command.

**Forbidden without explicit scope approval:**
- Pulling a real LLM into any engine (Anthropic/OpenAI/llama.cpp). That's a later, gated wave.
- Moving persona/presence logic into L1 or L4.
- Weakening the layer-boundary linter's allowlist.
- Modifying `planning/01_product_doctrine.md`.
- Force-pushing `dev` or `main`.

---

## 1. What already works (do not rebuild)

| Slice                     | Location                                      | Status                |
|---------------------------|-----------------------------------------------|-----------------------|
| 7-layer crate skeleton    | `packages/l1-…l7-*/`                          | trait surfaces live   |
| L5 policy engine          | `packages/l5-policy/`                         | Wave 3 evaluator, 5-stage, typed decisions |
| L5 durable mode           | `packages/l5-policy/` (feature `sqlite-backend`) | SqliteGrantLedger + SqliteAuditStore |
| L5 audit hash-chain + HMAC| `packages/l5-policy/src/audit_seal.rs`        | SHA-256 chain, HMAC-SHA256 seal, verify_chain |
| L1 turn FSM               | `packages/l1-interaction/src/turn.rs`         | 5-state subset: Idle→AwaitingPolicyApproval→{RouterDispatched→Completed \| blocked} |
| L1↔L4 bridge              | `apps/l1-cli/src/adapter.rs`                  | ModelRouterAdapter + ReflexModelRouter stub |
| L6 persona compiler       | `packages/l6-persona/src/default_compiler.rs` | Deterministic profile → 6 artifacts |
| Persona wired into demo   | `apps/l1-cli/src/persona.rs`                  | Tier + system prompt + output verbosity from persona |
| Boundary linter           | `tools/lint-layer-boundaries/`                | Activated, CI-blocking, 0 violations |
| CI                        | `.github/workflows/ci.yml`                    | rust / typescript / governance / legacy-python |

**Current test count:** `cargo test --workspace` = 0 failures across 35 test groups. `--features sqlite-backend` on L5 and L1 adds ~10 more.

**What is genuinely missing** (and which of the next sessions should close):

- No L2 memory. No context carries across turns.
- No L3 presence. No idle/active/away, no avatar-facing signal.
- No L7 trust UX. Ask tickets have no approve/deny surface.
- No audio path in L1. Utterances arrive as strings, not STT output.
- No real provider in L4. ReflexModelRouter echoes.
- Persona policy defaults compile but don't reach the engine config.
- `apps/desktop/` is still a scaffold (no Tauri shell yet).

---

## 2. Sequenced roadmap to "real companion" (next ~6 sessions)

Recommended order. Each is sized for one session; none require touching two engine crates.

### Session 1 — **L2.1 turn-scoped conversation memory**
Give the CLI actual continuity. New module in `packages/l2-memory/`:
- `ConversationStore` trait + in-memory impl storing (session_id, turn_id, utterance, response) tuples.
- Feature-gated sqlite-backed `SqliteConversationStore` using existing `aether-storage` substrate + a `0004_conversation_log.sql` migration.
- `TurnRequest` optionally carries a `Vec<PriorTurn>` context window, or the adapter fetches the last N turns before dispatching.
- Wire into `apps/l1-cli/` so `aether> repeat` returns the previous response. Demo proves continuity.
- Tests: write 3 turns, read back in order; cross-restart persistence.
- **Goal:** Aether stops being amnesiac. ~half-day.

### Session 2 — **L7.1 approval surface for Ask tickets**
Today the CLI prints `blocked: awaiting user approval (Ask ticket open)` and stops. Close the loop:
- New `packages/l7-trust/` slice: `ApprovalPrompt` + `ApprovalSink` traits.
- CLI implementation: when a turn returns `Decision::Ask`, prompt inline (`approve? [y/N]`), then call `PolicyEngine::respond_approval` with the captured `UserChoice`.
- Re-enter the turn FSM to dispatch the now-allowed call.
- Tests: ticket issued → user approves → turn resumes → Completed.
- **Goal:** `delete /tmp/foo` becomes a complete, human-in-the-loop flow.

### Session 3 — **L3.1 presence state machine**
First avatar-facing dimension. `packages/l3-presence/`:
- `PresenceState::{Idle, Listening, Thinking, Speaking, Away}`.
- Simple time-based scheduler driven by turn events.
- Consume `CompiledBehaviorMap.intensities` from L6 to weight transitions.
- CLI prints a `[presence: Thinking]` line each time the state changes.
- Tests: state progression across a turn, persona-intensity sensitivity.
- **Goal:** Aether has visible "attention" beyond text.

### Session 4 — **L4.1 real provider adapter (local llama.cpp or Ollama)**
Finally plug a real model behind the `ModelRouter` trait.
- New crate **outside** `packages/l4-router/` (e.g. `apps/l4-adapter-ollama/` or `packages/l4-router-adapters/ollama/`) so L4 core stays provider-free.
- HTTP client hitting local Ollama; implement `ModelRouter::route(tier, prompt)`.
- Swap `ReflexModelRouter` in the CLI adapter for the real one when a `--ollama http://localhost:11434 --model llama3` flag is passed.
- Tests: mock HTTP server fixture, assertion on request shape, error path.
- **Goal:** first real text generation end-to-end through the full stack. Gate behind a CLI flag so CI doesn't need a model.

### Session 5 — **Persona policy defaults → engine config**
Close the L6→L5 loop that's been typed but unused.
- Thread `CompiledPersona.policy_defaults.per_capability_defaults` into `EngineConfig` in `apps/l1-cli/`.
- Show that switching demo profile `stance` between Cautious / Bold actually changes which capabilities Auto vs Ask.
- Tests: same utterance, different stance, different Decision.
- **Goal:** persona isn't decoration; it shapes real policy outcomes.

### Session 6 — **Tauri desktop shell (v0)**
The first `apps/desktop/` that compiles. Minimal:
- Tauri 2 project in `apps/desktop/` with a single WebView rendering a transcript + input box.
- Tauri commands wrap the same `TurnEngine` the CLI uses — engine crates stay identical.
- No avatar, no presence UI yet — just a window where Don can type and see sealed audit IDs tick up.
- Tests: E2E via Tauri's driver if cheap; otherwise manual smoke checklist in the handoff.
- **Goal:** Aether leaves the terminal.

After session 6 you'll have: memory, approvals, presence signal, real model, persona-driven policy, and a window. That's a minimum-viable companion.

---

## 3. Hard constraints carrying into every session

- **Layer boundaries.** `python tools/lint-layer-boundaries/check.py` after every edit. Engines do not import each other; apps are the only glue point.
- **L5 is the single writer for side effects.** Memory writes, tool calls, file ops must all present a `Decision::Allow`.
- **Deterministic-first.** Until session 4 lands a real model, everything is deterministic and unit-testable. Don't introduce time/random/LLM nondeterminism earlier.
- **Commits are atomic and conventional.** `feat(<layer>): [WAVE/Slice] summary` plus a body explaining why. Co-authored-by line stays.
- **Run before claiming done.** `cargo fmt --all && cargo test --workspace && python tools/lint-layer-boundaries/check.py` before any commit you'd let Don see. Manually run the CLI after any demo-affecting change.
- **No pushes without explicit user approval** (per CLAUDE.md prime directives + session prompts).

---

## 4. Where to start next session (copy-paste)

```
You are Claude Code, working on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev (clean, at e7d2461, origin/dev matches; tag
v0.1.0-oss-preview.0 is published).

Read HANDOFF_2026-04-19_START_REAL_COMPANION_BUILD.md and begin
Session 1 — L2.1 turn-scoped conversation memory.

Do not push. Do not touch L5 or L6 internals. Do not pull in an LLM.
Stay inside packages/l2-memory/ + apps/l1-cli/ + one new migration
under packages/storage/migrations/.
```

Everything else the next session needs is in this file, the
execution reports, and the planning corpus under `planning/`. Good
luck.
