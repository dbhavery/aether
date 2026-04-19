# Wave 4 — Engine Stub Wave — Execution Report

**Date:** 2026-04-19
**Mode:** Additive, non-destructive. Load-bearing package shells. No engine logic.
**Prerequisites:** Waves 0–3 complete (L5 first-logic slice shipped in Wave 3).

---

## 1. Files / directories created or modified

### 1.1 New engine stub crates (6)

| Path | Key module layout |
|---|---|
| `file:///C:/Users/dbhav/Projects/aether/packages/l1-interaction/` | `Cargo.toml`, `README.md`, `src/{lib,engine,events,error}.rs`, `tests/smoke.rs` |
| `file:///C:/Users/dbhav/Projects/aether/packages/l2-memory/` | `Cargo.toml`, `README.md`, `src/{lib,kernel,error}.rs`, `tests/smoke.rs` |
| `file:///C:/Users/dbhav/Projects/aether/packages/l3-presence/` | `Cargo.toml`, `README.md`, `src/{lib,engine,error}.rs`, `tests/smoke.rs` |
| `file:///C:/Users/dbhav/Projects/aether/packages/l4-router/` | `Cargo.toml`, `README.md`, `src/{lib,router,error}.rs`, `tests/smoke.rs` |
| `file:///C:/Users/dbhav/Projects/aether/packages/l6-persona/` | `Cargo.toml`, `README.md`, `src/{lib,compiler,error}.rs`, `tests/smoke.rs` |
| `file:///C:/Users/dbhav/Projects/aether/packages/l7-trust/` | `Cargo.toml`, `README.md`, `src/{lib,shell,error}.rs`, `tests/smoke.rs` |

### 1.2 Planning additions

- `file:///C:/Users/dbhav/Projects/aether/planning/00_VISION_AND_GUARDRAILS.md` — **canonical Aether vision & guardrails doctrine**. Authored by Don; saved verbatim to planning root. Declared to sit **above** `01_product_doctrine.md` in the planning hierarchy: conflicts resolve in favor of `00_` until a `DECISION_LOCK_PASS_*.md` updates it. Change control spelled out in the doc itself.

### 1.3 Governance edits

- `file:///C:/Users/dbhav/Projects/aether/Cargo.toml` — 6 new workspace members appended to `[workspace].members`.
- `file:///C:/Users/dbhav/Projects/aether/.github/CODEOWNERS` — 6 new layer-crate ownership lines activated; coordinator-owned until layer agents are assigned.

### 1.4 Not modified

- `packages/event-bus/` — Wave 4 did not need it (L5 uses its own `L5EventSink` trait per Wave 3).
- `packages/storage/` — Wave 4 did not touch it; `aether-storage` is a path dep only on `l2-memory` for future use.
- `tools/`, `pnpm-workspace.yaml`, any TS package, any legacy Python tree.

---

## 2. Per-package shape summary

Every crate follows the same skeleton:
- `#![deny(unsafe_code)]`
- `#![warn(missing_docs)]`
- `#![allow(dead_code)]` (scaffold period)
- `thiserror`-based `L*Error` enum
- Small smoke test asserting cardinality of locked enums (e.g. `assert_eq!(TurnState variants, 19)`).
- Path-dep on `aether-l5-policy` wherever layer events / types are needed.

### 2.1 `aether-l1-interaction`

- `TurnId`, `TurnState` (**19 variants**), `ReflexClass` (4), `TimingBudgets` with doctrine defaults.
- Traits: `ReflexClassifier`, `Stt`, `Tts`, `ModelRouterClient`, `PresenceClient`, `InteractionEngine`.
- `InteractionEvent` sum + `InteractionEventKind` (14 shapes; 5 concrete payloads wired, 9 kinds named).
- `L1Error` (ReflexBudget, Stt, Tts, Router, Policy, Internal).
- Path deps: `aether-l5-policy` (imports `Capability`, `Decision`, `ResourceScope` into `InteractionEngine::on_policy_decision`).

### 2.2 `aether-l2-memory`

- `MemoryId`, `EmbeddingRef`, `MemoryDomain` (**6** — Personal, Work, Health, Finance, Creative, System), `PrivacyClass` (4), `RetentionKind` (Ephemeral/Session/Days(u16)/Permanent), `ProvenanceTag` (7 — matches L5's consumer contract 1:1).
- `MemoryItem` struct with content_ref/content_inline discriminants + embedding_ref.
- Traits: `MemoryKernel`, `EmbeddingStore`.
- `L2Error` (NotFound, Storage, Embedding, PrivacyViolation, Internal).
- Path deps: `aether-l5-policy`, `aether-storage`.

### 2.3 `aether-l3-presence`

- `PresenceTier` (Lite/Balanced/Pro), `BehaviorClass` (**9** — Idle, Listening, Thinking, Speaking, BargingIn, Emphasizing, Deflecting, Repairing, SigningOff), `BehaviorFrame` (t_ns, behavior, blink, gaze, mouth, viseme).
- Traits: `RenderingSurface`, `PresenceEngine`.
- `L3Error`.
- No path dep on L5 (presence doesn't authorize).

### 2.4 `aether-l4-router`

- `ProviderId`, `RouterTier` (**7** — Reflex, LocalTiny, LocalSmall, LocalFull, RemoteStandard, RemotePremium, RemoteDeepResearch), `ToolCall`, `ToolResult`, `ToolError`.
- Traits: `ProviderAdapter`, `ModelRouter`.
- `L4Error` includes `PolicyDenied`, `ReEvalRequired`, `CostCapHit` — matching L5's locked Decision-4 + Decision-5 pathways.
- Path deps: `aether-l5-policy` (imports `Capability`, `Decision`, `ResourceScope` into `ToolCall` shape).

### 2.5 `aether-l6-persona`

- `PersonaId`, `PersonaPack` (raw YAML body carried as `serde_json::Value` for Wave 4; real typed schema expands in Wave 5 against `planning/17_persona_pack_schema.md`).
- **6 compiled artifact structs** — `CompiledPrompts`, `CompiledRoutingRules`, `CompiledBehaviorMap`, `CompiledMemoryHints`, `CompiledToolAllowList`, `CompiledVoiceConfig` — composed into `CompiledPersona` which **includes `PersonaCompiledPolicyDefaults` from `aether_l5_policy`** (honors the L5 interface-pack §3.4 contract).
- Hot-reload state machine: `SwapState` (**6** — Idle, Compiling, Validating, ReadyToCommit, Committing, RolledBack).
- Trait: `PersonaCompiler` (`compile`, `begin_swap`, `swap_state`, `commit_swap`).
- `L6Error` (InvalidSignature, Schema, InvariantViolation, SwapState, Internal).
- Path deps: `aether-l5-policy`.

### 2.6 `aether-l7-trust`

- **Backend surfaces only.** UI implementation lives in `apps/desktop/` (future wave).
- `ApprovalPrompt`, `PostureBanner`, `OnboardingScreen` (**8** — Welcome, PersonaPicker, PresetPicker, CapabilityPreview, PrivacyPledge, ByokSetup, FirstTurn, Done), `OnboardingState`.
- Trait: `ShellAdapter` — `present_approval`, `render_posture_banner`, `emit_to_webview`, `on_late_decision` (optimistic-UI rollback hook from L7-T02).
- `L7Error` includes `SecretLeak` (hard-fail per L7-T03 of the test matrix).
- Path deps: `aether-l5-policy`.

---

## 3. Dependency-direction compliance (guardrail §4.1)

All Wave 4 crates honor the locked direction rules from `planning/00_VISION_AND_GUARDRAILS.md` §4.1:

| Crate | Depends on | Does NOT depend on |
|---|---|---|
| l1-interaction | l5-policy (contracts) | l2, l3, l4, l6, l7 |
| l2-memory | l5-policy (contracts), storage | l1, l3, l4, l6, l7 |
| l3-presence | — | any sibling layer |
| l4-router | l5-policy (contracts) | l1, l2, l3, l6, l7 |
| l6-persona | l5-policy (contracts only) | l1, l2, l3, l4 (outputs reach them through bus) |
| l7-trust | l5-policy (contracts) | l1, l2, l3, l4, l6 (only through events / bridges) |

**Zero sibling-layer imports** across the 6 crates. When `cargo-deny`'s `[bans]` block in `tools/lint-layer-boundaries/deny.toml` is activated, the `wrappers = ["aether-l5-policy"]` rule already stubbed out becomes a one-line activation — no refactor needed.

---

## 4. Checks run

| Check | Result |
|---|---|
| TOML syntax — all 6 new `Cargo.toml` + root workspace | **PASS** (`tomllib.loads`) |
| `pnpm -r --if-present typecheck` (3 TS packages) | **PASS** |
| Structural: every crate ships `Cargo.toml` + `src/lib.rs` + `README.md` + `tests/smoke.rs` | **PASS** |
| `cargo check --workspace` | **Deferred** — no `rustup` on the dev machine (same status as Waves 2/3). Wave 3.5 remains the gating step for a full Rust compile. |

Rust hand-audit: every `use` path checked against actual re-exports in `aether-l5-policy` lib.rs. No `&'static str` fields in serde-derived structs. Every trait is object-safe (checked — no generic methods, no associated-constant returns, no `Self: Sized` where a `dyn` reference would be wanted). `L6Error::InvalidSignature` and `L7Error::SecretLeak` are explicitly named so test matrix entries can assert against them.

---

## 5. Vision & guardrails drift check

> Did this Wave change the vision or guardrails?

**No.** Wave 4 is the first wave after `planning/00_VISION_AND_GUARDRAILS.md` was added, and the scaffolds **comply** with every guardrail:

| Guardrail | How Wave 4 honors it |
|---|---|
| §2.2 — 7-layer non-negotiable | 6 new crates, one per non-L5 must-own layer (L1, L2, L3, L4, L6, L7). |
| §2.5 — Rust-first engines | All 6 crates are Rust. Only L7 has an optional TS facade (deferred to a later wave, only if Tauri bindings demand it). |
| §3.2 — No collapsing layers | Each crate's trait surface stays inside its layer; no sibling imports. |
| §3.5 — No ad-hoc cross-package deps | Only permitted direction is `l*` → `aether-l5-policy` (contracts only). Enforceable by `tools/lint-layer-boundaries/deny.toml` one-line activation. |
| §4.1 — Direction of dependencies | See §3 table in this report — compliant. |
| §4.3 — Monorepo discipline | Every engine lives under `packages/`. |
| §5.1 — Waves, not thrash | Wave 4 has a name, a dated report, and an updated roadmap (§8). |
| §5.2 — Scaffold before logic | This wave scaffolds only; logic is explicitly deferred. |
| §5.3 — Roadmap graphic | §8 below. |

New doc added to planning, but **no existing doctrine was modified**. Doctrine did not drift.

---

## 6. What remains for each layer to be "v1 complete"

Deferred — the checklist every layer agent will work through in subsequent waves:

- **L1:** implement the 19-state turn FSM driver, reflex classifier stub, STT/TTS adapter wiring to `packages/media-engine`, policy-gate integration against `DefaultPolicyEngine`.
- **L2:** SQLite-backed `DefaultMemoryKernel` (depends on Wave 3.5 rusqlite wire-up), `EmbeddingStore` adapter against a vector backend (LanceDB candidate), provenance-tag pipeline delivering `ProvenanceTag`s to L5 on every memory hit.
- **L3:** 30–60 Hz scheduler loop, Three.js rendering surface for OSS Preview, viseme-sync against `packages/media-engine` TTS chunk stream.
- **L4:** `DefaultModelRouter` with per-tool-call `PolicyEngine::evaluate`, Anthropic / OpenAI / Ollama provider adapters, `CostEvent` emission on every completion, Decision-4 per-step re-eval engine honoring the 8-trigger list.
- **L6:** deterministic YAML → typed artifact compiler, signature verification for privileged overlays, hot-reload state machine driver, `persona_swap_commit` bus event emission into L5.
- **L7:** onboarding state machine driver, approval-renderer integration tests against `DefaultPolicyEngine`, posture-banner event coalescing, Tauri `ShellAdapter` implementation inside `apps/desktop/`.

---

## 7. Commit strategy

Single focused commit:

```bash
cd C:/Users/dbhav/Projects/aether
git add packages/l1-interaction/ packages/l2-memory/ packages/l3-presence/ \
        packages/l4-router/    packages/l6-persona/  packages/l7-trust/ \
        Cargo.toml .github/CODEOWNERS \
        planning/00_VISION_AND_GUARDRAILS.md \
        WAVE4_EXECUTION_REPORT_2026-04-19.md
git commit -m "feat(engines): [WAVE4] engine stubs L1/L2/L3/L4/L6/L7 + vision doctrine"
git push origin dev
```

If you prefer to separate the doctrine doc:

```bash
git add planning/00_VISION_AND_GUARDRAILS.md
git commit -m "docs(planning): add 00_VISION_AND_GUARDRAILS doctrine"
# then the engine-stub commit
```

---

## 8. Roadmap graphic — after Wave 4

```text
AETHER ROADMAP STATUS — AFTER WAVE 4 (2026-04-19)

FOUNDATION / DOCTRINE
[██████████] 100%  Vision & guardrails (00_VISION_AND_GUARDRAILS) — NEW this wave
[██████████] 100%  Product doctrine (01_product_doctrine)
[██████████] 100%  7-layer model aligned
[██████████] 100%  5 control-plane decisions locked

DESIGN / PREP
[██████████] 100%  L1–L7 system designs
[██████████] 100%  L1–L7 interface packs
[██████████] 100%  Event contracts master
[██████████] 100%  SQLite schema pack (DDL drafted)
[██████████] 100%  Test matrix master
[██████████] 100%  Implementation handoff notes

REPO / INFRA
[██████████] 100%  Wave 0 — monorepo assimilation
[██████████] 100%  Wave 1 — workspace + shared infra + governance
[██████████] 100%  Wave 2 — L5 scaffold (types, traits, 16-command IPC surface)

L5 — POLICY ENGINE
[████████░░]  80%  Wave 3 — first real logic slice (in-memory ledger + audit + evaluator)
[░░░░░░░░░░]   0%  Wave 3.5 — rusqlite persistence wire-up
[░░░░░░░░░░]   0%  Wave 4.5 — audit hash-chain + HMAC + keyring
[░░░░░░░░░░]   0%  Wave 4.5 — BYOK cost-cap Stage 0 + remaining 6 re-eval triggers

OTHER ENGINES — STUB SHELLS (Wave 4)  ← you are here
[██████████] 100%  L1 interaction/timing — traits + 19-state TurnState + events + error
[██████████] 100%  L2 memory kernel — traits + 6 domains + MemoryItem + provenance
[██████████] 100%  L3 presence — traits + 9 behavior classes + BehaviorFrame + 3 tiers
[██████████] 100%  L4 router — traits + 7 tiers + ToolCall vocabulary
[██████████] 100%  L6 persona compiler — traits + 6 compiled artifacts + SwapState
[██████████] 100%  L7 trust UX backend — ShellAdapter + 8-screen onboarding + ApprovalPrompt

OTHER ENGINES — LOGIC WAVES (future)
[░░░░░░░░░░]   0%  L1 first-logic slice (turn FSM + reflex classifier + STT/TTS wiring)
[░░░░░░░░░░]   0%  L2 first-logic slice (SQLite kernel + embedding adapter)
[░░░░░░░░░░]   0%  L3 first-logic slice (scheduler + Three.js surface)
[░░░░░░░░░░]   0%  L4 first-logic slice (provider adapters + per-call policy gate)
[░░░░░░░░░░]   0%  L6 first-logic slice (deterministic compile + hot-reload)
[░░░░░░░░░░]   0%  L7 first-logic slice (onboarding driver + Tauri shell adapter)

PRODUCT INTEGRATION
[░░░░░░░░░░]   0%  apps/desktop (Tauri shell, OSS Preview + Pro flags)
[░░░░░░░░░░]   0%  apps/guest (Cloudflare Worker + Groq endpoint)
[░░░░░░░░░░]   0%  apps/docs-site
[░░░░░░░░░░]   0%  End-to-end onboarding → first-turn flow

TOOLING / LINTS
[████░░░░░░]  40%  tools/lint-layer-boundaries (deny.toml ready; uncomment bans post-Wave 4)
[████░░░░░░]  40%  tools/lint-policy-bypass (L5-aligned rules doc; linter prototype pending)
[██░░░░░░░░]  20%  tools/lint-private-asset-leak (strategy only)
[██░░░░░░░░]  20%  tools/ts-bindings-gen (placeholder)

HIGH-CONFIDENCE NEXT SESSIONS
  1. Wave 3.5 — install rustup + add rusqlite to `packages/storage` + swap L5
                in-memory backends behind a feature flag + first real
                `cargo check --workspace`.
  2. Wave 4.1 — activate `tools/lint-layer-boundaries/deny.toml` `[bans]` list
                now that all 6 sibling-layer crates exist; enforces the
                no-cross-layer-import rule that Wave 4 manually respected.
  3. Layer first-logic wave of your choice (L1 turn FSM is highest leverage —
                unblocks end-to-end demo through L5 → L4 stub → L1 loop).
```

---

## 9. Non-destructive guarantee

No legacy / v1.0 file was modified. No existing planning doc was edited (the new `00_VISION_AND_GUARDRAILS.md` is a pure addition; no edits to `01_product_doctrine.md` or any other planning file). `Cargo.toml` and `CODEOWNERS` edits are additive (appending members / ownership lines). Every new file is in a new directory under `packages/`. Wave 3 Rust code is untouched; Wave 3's 10 tests remain valid and unaffected.
