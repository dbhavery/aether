---
status: working
date: 2026-04-18
last-updated: 2026-04-18
role: canonical planning basis for X1 (monorepo) until superseded
owner: X1 (repo restructure agent) — coordinator-accepted as working baseline
depends_on:
  - 01_product_doctrine.md
  - plans/00_ORCHESTRATION_MAP.md
  - OPEN_QUESTIONS.md §Repo structure [DECIDED 2026-04-18]
  - 16_tech_stack.md
blocked_by:
  - sibling-repo fate decision (aether-desktop-voice/, aether-frontend-ux/, aether-personas/)
  - Isabelle_Kunstig disposition (parallel vs in-tree)
  - final product naming (affects top-level app folder names)
---

# Monorepo Plan — Draft

Concrete top-level layout, 7-layer mapping, cross-cutting stream placement, guardrails, and migration sketch for the Aether family monorepo. Planning pass only — no file moves, no code writes.

This document is the upstream for `MIGRATION_PLAN.md` (to live at the new repo root once approved) and for X1's execution prompt (`prompts/X1_repo_restructure.md`).

---

## 1. Top-level layout

Single repo. Canonical root name TBD pending product naming lock; working name `aether/`.

```
aether/
├── apps/              # shippable end-products (desktop, mobile, docs site, guest endpoint)
├── packages/          # reusable libraries — the 7 must-own layers + shared UI + shared types
├── infra/             # deployment / ops config (Tauri bundling, signed updater channels, installer)
├── tools/             # dev tooling, codegen, lint, agent scaffolds, scripts
├── planning/          # this planning corpus (doctrine, layer plans, roadmaps)
├── research/          # non-doctrinal references, inbox, spikes, retired v1.0 docs
├── docs/              # user-facing docs + trust-center source + release notes
├── personas/          # first-party persona packs (public) — private packs live outside repo
├── .github/           # PR templates, issue templates, CODEOWNERS, (CI left for later)
├── Cargo.toml         # Rust workspace root
├── package.json       # TS/pnpm workspace root
├── pnpm-workspace.yaml
├── rust-toolchain.toml
├── README.md
└── CLAUDE.md          # repo-level operating rules for AI agents
```

| Folder | Purpose | Example contents | Owner |
|---|---|---|---|
| `apps/` | End-user products; each app is a thin shell that composes packages. | `apps/desktop/` (Tauri Pro+OSS), `apps/guest/` (Cloudflare Worker + Groq endpoint), `apps/mobile/` (React Native, later), `apps/docs-site/` (trust center + marketing) | App-owner per app; desktop is jointly owned by L7 (UI) + X3 (shell) |
| `packages/` | Reusable libraries. 7-layer moat code + shared UI kit + shared types live here. | `packages/l1-timing/`, `packages/l5-policy/`, `packages/ui-kit/`, `packages/types/`, `packages/event-bus/` | One layer agent per layer package; shared packages coordinator-owned |
| `infra/` | Build, bundling, signed updater, installer scaffolds, OS-specific packaging. | `infra/tauri/`, `infra/installer-inno/` (OSS Preview), `infra/updater/`, `infra/codesign/` | X3 Tauri architecture |
| `tools/` | Developer tooling — codegen, lints, agent scaffolds, pack-scaffold CLI, persona audit CLI. | `tools/persona-scaffold/`, `tools/ts-bindings-gen/`, `tools/lint-policy-bypass/` | Cross-cutting; each tool has a named owner in CODEOWNERS |
| `planning/` | Doctrine + layer plans + orchestration map. Source of truth for how the product is built. | Current `aether-planning/*` contents, restructured. | Don (coordinator); agents propose edits |
| `research/` | Non-doctrinal references, inbox drops, spikes, retired v1.0 docs. | Current `inbox_2026-04-18b/`, `archive/`, `sources_matrix.md` merged contents. | Coordinator |
| `docs/` | User docs, trust-center content, release notes. | Onboarding info-explainers, capability docs, release changelog | L7 primary; coordinator for release notes |
| `personas/` | Public first-party persona packs. | `personas/aurora/`, `personas/sage/` | L6 compiler owns schema; persona authors ship packs |

**Private Isabelle overlay** lives outside this repo (separate private-only path) and is merged at build time for Don's personal profile — never shipped in public distributables. See §3.2.

---

## 2. Seven must-own layers mapped to packages

Each layer is exactly one primary package. Rust crates where latency/safety-critical; TS packages where UI/authoring-surface. Most layers have both — a Rust core + a TS facade generated from typed bindings.

| Layer | Primary package(s) | Runtime | Consumes | Produced events |
|---|---|---|---|---|
| **L1 Interaction timing (+ reflex)** | `packages/l1-timing/` (Rust core + TS facade) | Rust event-loop thread | `event-bus`, `l2-memory` hits, `l4-router` decisions, `l5-policy` allow | `intent_hint`, `ack_phrase`, `route_decision`, `turn_state` |
| **L2 Memory kernel** | `packages/l2-memory/` (Rust) + `packages/l2-memory-ts/` (read-only TS views) | Rust + SQLite + vector index | `l5-policy` (gated reads/writes), `l6-persona` (salience rules) | `memory_hit`, `memory_write`, `provenance_update` |
| **L3 Presence engine** | `packages/l3-presence/` (Rust) + `packages/l3-avatar-ui/` (TS/React + WebGL shim) | Rust presence controller + rendering adapter | `l1-timing` turn state, `l6-persona` visual params, media engine visemes | `presence_state`, `avatar_frame_ready` |
| **L4 Model router** | `packages/l4-router/` (Rust) | Rust async runtime | `l2-memory` confidence, `l5-policy` tool gate, `l6-persona` tier prefs | `route_decision`, `escalation_reason`, `cost_event` |
| **L5 Policy engine** | `packages/l5-policy/` (Rust, language of record) + `packages/l5-policy-ts/` (typed bindings for UI) | Rust decision engine; SQLite audit log | persona defaults from `l6-persona`; nothing else | `action_request`, `policy_decision`, `approval_pending`, `grant_*`, `audit_record` |
| **L6 Persona compiler** | `packages/l6-persona/` (Rust) + `packages/l6-persona-ts/` (TS types from ts-rs) | Rust loader+compiler; serde YAML | `17_persona_pack_schema` rules | `persona_swap_begin`, `persona_swap_commit`, `compiled_persona_ready` |
| **L7 Trust UX + onboarding** | `packages/l7-onboarding/`, `packages/l7-trust-center/`, `packages/ui-kit/` (shared design system) | TS/React inside Tauri webview | `l5-policy` prompts, `l6-persona` picker, `l2-memory` review, `l4-router` disclosures, `l1-timing` first-run | n/a (consumer layer) |

### Shared infra packages (not layer-specific)

| Package | Purpose | Owner |
|---|---|---|
| `packages/event-bus/` | Typed Rust event bus + TS bridge. Every layer consumes. | X3 (jointly with L1) |
| `packages/types/` | Shared TS types generated from Rust (ts-rs). Compiled persona, policy decisions, turn states. | Coordinator; auto-generated |
| `packages/ui-kit/` | Custom design-system primitives (tokens, components). Dark, neumorphic monochrome per §05. | L7 |
| `packages/media-engine/` | STT/TTS/VAD integration; streaming chunks, viseme timing. Borrowed models, custom control. | X3 adjunct |
| `packages/storage/` | SQLite schema, migrations, encryption-at-rest, audit-chain primitives. | Coordinator; L2 + L5 review |
| `packages/telemetry/` | OpenTelemetry wrapper; local-only by default. | Coordinator |

### Internal dependency graph (who imports whom)

```
ui-kit     ← l7-*, apps/desktop
types      ← every TS package
event-bus  ← every layer runtime
storage    ← l2-memory, l5-policy
media-engine ← l3-presence, l1-timing (VAD hook)
l6-persona ← l1-timing, l2-memory, l3-presence, l4-router, l5-policy, l7-onboarding
l5-policy  ← l1-timing, l2-memory, l4-router, l7-* (approval UI)
l2-memory  ← l1-timing (reflex hints), l4-router (confidence)
l4-router  ← l1-timing (route_decision target)
l1-timing  ← l3-presence (state consumer)
```

No layer imports a sibling layer directly at package level — coordination happens through `event-bus` or through the typed `l6-persona` / `l5-policy` outputs. This is the enforceable boundary rule (see §4).

---

## 3. Cross-cutting streams

### 3.1 X1 — Repo restructure mechanics

- X1 owns `MIGRATION_PLAN.md` at repo root and the first migration PR series.
- Workspace configs (`Cargo.toml` root, `pnpm-workspace.yaml`, `rust-toolchain.toml`) are X1's first deliverables; no package creation is accepted before these land.
- Moves happen in named waves (see §5). X1 is the single writer during a wave.

### 3.2 X2 — Isabelle migration

- Isabelle is a **privileged persona profile**, not a separate codebase (doctrine §8).
- `Isabelle_Kunstig/` stays live in parallel during phased overlap; capability-by-capability parity checks written into `plans/X2_isabelle_inventory.md`.
- Private Isabelle assets (persona pack, memory, integrations) live at a path outside this repo; referenced by the compiler via the privileged-profile overlay mechanism (L6 §Privileged-profile isolation).
- Build-time lint in `tools/lint-private-asset-leak/` prevents Isabelle assets entering OSS Preview or Pro public distributables.
- Cutover gate per domain: feature parity + test parity + Don's sign-off before retiring the Isabelle_Kunstig side.

### 3.3 X3 — Tauri desktop shell

- Single `apps/desktop/` app serves both OSS Preview and Aether Pro — differentiated by build flags, not separate trees. A `--product=oss|pro` compile-time switch gates Pro-only features (Email capability, full preset ladder, etc.).
- Tauri backend is a Rust crate living under `apps/desktop/src-tauri/` and it composes the 7-layer packages; zero business logic in the shell itself.
- Signed updater + code-sign keys + installer scaffolds all in `infra/`.
- pywebview explicitly **not** present in the monorepo unless Don authorizes a tactical OSS-Preview-only escape hatch. If authorized, it lives at `apps/desktop-pywebview-fallback/` clearly marked deprecated-on-arrival.

### 3.4 Shared trust/perms components

- Permission prompt, approval UI, trust center, capability-matrix editor, action-history replay — all in `packages/l7-trust-center/`, composed by `apps/desktop/`.
- The prompt renderer subscribes to `l5-policy`'s `approval_pending` event; it does not call `l5-policy` directly. This preserves single-writer rule on policy decisions.

---

## 4. Guardrails

### 4.1 Boundary enforcement (not convention — tooling)

1. **Rust workspace rule:** each layer crate declares its allowed `dependencies` explicitly. Sibling-layer imports forbidden. Enforced by `cargo-deny` + a custom `tools/lint-layer-boundaries/` check in CI-phase (follow-on).
2. **TS workspace rule:** `pnpm` project references + an ESLint custom rule (`no-cross-layer-import`) that rejects any `import` from `packages/l*` into another `packages/l*`. UI apps may import any TS package; layer packages may not import UI.
3. **Policy-bypass lint:** `tools/lint-policy-bypass/` scans for direct executor calls (file I/O, network, subprocess) from anywhere outside `packages/l5-policy/`-approved execution paths. Blocking.
4. **Private-asset leak lint:** `tools/lint-private-asset-leak/` fails builds if any Isabelle-tagged asset ends up in a public distributable manifest.
5. **CODEOWNERS** per folder so agent PRs can't be merged without the owning agent's approval.

### 4.2 How agents add new packages or apps

- **No unilateral creation.** Agent opens a PR that only updates `planning/` and `MIGRATION_PLAN.md` with the proposed package (name, purpose, dependency list, owner). Don approves.
- After approval, X1 (or the owning layer agent) creates the skeleton in a single follow-up PR: `Cargo.toml` / `package.json` entry, minimal lib target, README, CODEOWNERS line, zero business logic.
- Only then may implementation PRs land against the new package.
- New cross-layer dependency → requires coordinator review, because it is a boundary decision, not an implementation choice.

### 4.3 Doctrine and planning files sit alongside code without getting lost

- `planning/` is part of the repo, versioned, reviewed via PR. Layer plans evolve with the code that implements them — not on a separate doc site.
- `planning/01_product_doctrine.md` is coordinator-only-write. Agents propose edits via flagged-conflict notes; never commit doctrine rewrites.
- Root `README.md` points to `planning/README.md` as the index.
- Root `CLAUDE.md` contains the operating rules for AI agents working in the repo (one-layer-per-session rule, conflict-escalation protocol, link format).
- `docs/` is user-facing and copy-edited; `planning/` is internal and terse; they do not overlap.

---

## 5. Migration sketch (high-level)

Assumes all decisions in §0 frontmatter `blocked_by` are resolved before Wave 1.

### Wave 0 — Repo genesis (coordinator + X1, 1 session)

1. Create new repo `aether/` at `file:///C:/Users/dbhav/Projects/aether/` (or chosen canonical path).
2. Initialize workspace configs (Cargo, pnpm, rust-toolchain).
3. Create empty `apps/`, `packages/`, `infra/`, `tools/`, `planning/`, `research/`, `docs/`, `personas/` skeletons with README stubs.
4. Move `aether-planning/` contents into `planning/` in a single commit, preserving history via `git mv` or subtree merge.
5. Land root `README.md`, `CLAUDE.md`, `CODEOWNERS`, `.gitignore`.
6. Freeze: no other work until this is approved.

**Risk:** history loss during subtree merge. **Mitigation:** use `git subtree add` with explicit prefix; verify log counts before deleting source.

### Wave 1 — Shared infra scaffolds (X1 + X3)

1. Create empty `packages/event-bus/`, `packages/types/`, `packages/storage/`, `packages/ui-kit/`, `packages/media-engine/`, `packages/telemetry/` with typed stubs only.
2. Land `tools/ts-bindings-gen/` so layer agents have codegen available.
3. Install boundary-lint tooling (`tools/lint-layer-boundaries/`, `tools/lint-policy-bypass/`, `tools/lint-private-asset-leak/`) with initial permissive rules; tighten in Wave 3.
4. No layer code yet.

**Risk:** premature shared-infra design locks layers into an ill-fitting bus. **Mitigation:** stubs only; contracts ratified after Wave 2 draft.

### Wave 2 — Layer skeletons (L1–L7 agents in parallel)

1. Each layer agent creates their package(s) per §2 with `lib.rs` stubs, public interface sketches, zero logic.
2. Event contracts proposed in each package's README; coordinator reconciles into `packages/event-bus/CONTRACTS.md`.
3. Contracts freeze at coordinator sign-off.

**Risk:** 7 agents proposing incompatible event shapes. **Mitigation:** coordinator-gated freeze; boundary-lint tool enforces after freeze.

### Wave 3 — v1.0 content port + Isabelle inventory (X4 + X2)

1. X4 ports the 5 priority v1.0 artifacts (8-screen wizard, Guest mode, cost UX, distribution playbook, Inno scaffold) into the right apps/packages.
2. X2 writes `plans/X2_isabelle_inventory.md` enumerating every capability Isabelle_Kunstig currently has; parity contracts drafted.
3. Sibling repos (`aether/`, `aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/`) triaged per Don's decision — archive to `research/archive/2026-04_v1_repos/` or delete.

**Risk:** sibling repos contain unique ideas not yet captured. **Mitigation:** X4 explicit inventory pass before any archive/delete.

### Wave 4 — First implementation (layer agents, phased per `plans/01_pro_phase_crosswalk.md`)

1. Phase 0 gate: L5 capability taxonomy + audit-log format frozen; L2 memory schema frozen; L6 compiler I/O frozen.
2. Layer agents ship P0 (OSS Preview-shaped) implementations against their packages.
3. `apps/desktop/` composes packages behind `--product=oss` build flag.
4. OSS Preview demo-able off the monorepo; pywebview fallback only if Don explicitly authorizes.

**Risk:** layer agents block on each other's unfinished contracts. **Mitigation:** each layer ships a stub adapter against any unready upstream per orchestration-map §7 contingencies.

### Wave 5 — Pro onward, Isabelle cutover per domain

Phases 1–6 per `plans/01_pro_phase_crosswalk.md`; Isabelle domains cut over as parity verified; no indefinite parallelism.

**Risk points (cumulative):**
- Git history discontinuity (Wave 0) — mitigate with subtree preservation.
- Contract drift between Rust core and TS facade (Wave 2+) — mitigate with generated bindings, single source of truth in Rust.
- Policy-bypass regression after lint relaxations (Wave 4+) — mitigate by CI blocking and red-team suite.
- Isabelle asset leak into public distributable (Wave 5) — mitigate with private-asset-leak lint + manifest diff.

---

## 6. Open questions and assumptions

### Open (blocking Wave 0–1)

1. **Canonical repo path and final name.** Working `file:///C:/Users/dbhav/Projects/aether/` but OPEN_QUESTIONS lists Aether Pro / Core / One still open. Repo name chosen independently of the product marketing name?
2. **Sibling repo fate.** `aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/` — archive inside repo under `research/archive/`, archive outside repo, or delete?
3. **Isabelle_Kunstig physical location.** Stays where it is during phased overlap, or moves under `apps/isabelle-legacy/` inside the monorepo for visibility?
4. **History preservation policy.** `git subtree add` (preserves) vs flat import (loses history but cleaner). Default: preserve.

### Open (deferable to Wave 2–3)

5. OSS Preview vs Pro build-flag strategy — `--product=oss|pro` Cargo feature flag vs separate entrypoints.
6. `personas/` — ship first-party public packs inside the repo, or fetch at runtime? Default: in-repo for first-party; external for user-imported.
7. Whether `docs/` is user-facing HTML site or plain markdown consumed by the trust center — likely both, with `apps/docs-site/` rendering from `docs/`.
8. Mobile app path — `apps/mobile/` reserved but empty until mobile stack decided (see OPEN_QUESTIONS).
9. Whether `tools/` agent scaffolds (self-contained briefing packs, one-shot prompts) live inside the repo or in Don's personal `.claude/` tree. Default: repo-resident so they travel with the code.

### Assumptions (explicit)

- **A1.** Monorepo uses Rust workspace + pnpm workspaces + single toolchain pinning. No nested independent repos.
- **A2.** Every layer package exposes a stable public interface; sibling-layer imports forbidden at tooling level from Wave 3 onward.
- **A3.** Isabelle never forks the codebase; she is always a privileged persona profile + private asset overlay over Aether Pro.
- **A4.** OSS Preview and Aether Pro share `apps/desktop/` with feature-flagged divergence, not separate app trees.
- **A5.** Planning corpus (`planning/`) lives inside the repo and is PR-reviewed like code.
- **A6.** Private Isabelle overlay path sits outside the repo and is never committed; the compiler resolves it at runtime for Don's profile only.
- **A7.** CI/CD pipeline design is a follow-on deliverable (out of scope here), but the boundary-lint tooling in `tools/` is scaffolded in Wave 1 so that whenever CI lands, it has jobs to run.

---

## 7. Reference specs

- file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether-planning/16_tech_stack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md
- file:///C:/Users/dbhav/Projects/aether-planning/OPEN_QUESTIONS.md
- file:///C:/Users/dbhav/Projects/aether-planning/SESSION_END_INDEX_2026-04-18b.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing.md through L7_trust_ux_onboarding.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/01_pro_phase_crosswalk.md
