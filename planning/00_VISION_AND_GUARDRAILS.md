# Aether — Vision & Guardrails

> **Status:** Canonical. Single source of truth for high-level vision and guardrails. Sits above `01_product_doctrine.md`; where this file and any other planning file conflict, this file wins until a `DECISION_LOCK_PASS_*.md` updates it.
> **Added:** 2026-04-19 (Wave 4 session, Don-authored).
> **Change control:** updates require an explicit entry in a `DECISION_LOCK_PASS_*.md` AND a note in the corresponding Wave execution report.

---

## 1. One-sentence vision

Aether is a **local-first, desktop-native AI companion** that feels like a real presence: it remembers, reasons, speaks, and acts within a strict policy and trust framework, not just a chat window.

## 2. Core principles

1. **Companion, not chatbot**
   - Long-lived relationship, not single-session Q&A.
   - Conversational timing, presence, and memory matter as much as answer quality.

2. **Seven-layer architecture is non-negotiable**
   - L1: Interaction / timing / reflex
   - L2: Memory kernel
   - L3: Presence scheduler
   - L4: Model & tool router
   - L5: Policy engine (control plane)
   - L6: Persona compiler
   - L7: Trust, onboarding, and user controls
   Each layer has clear responsibilities and must not absorb others "for convenience."

3. **Local-first by default**
   - User data, memory, and persona state live locally first.
   - Remote calls (models, tools, research) are deliberate, visible, and policy-governed.

4. **Desktop-first product**
   - Primary surface is a desktop app (Tauri long-term, pywebview tactical for OSS preview).
   - Browser UI is an implementation detail, not the core product.

5. **Rust-first for engines and infra**
   - Timing, policy, storage, routing, and memory engines are primarily Rust crates.
   - TypeScript is used for UI, bindings, and light orchestration — not for core control logic.

6. **Policy and trust are load-bearing**
   - L5 is a first-class engine: all high-impact actions route through it.
   - Audit, cost caps, and grants are modeled explicitly, not bolted on later.

7. **Monorepo with explicit contracts**
   - Single repo, multiple packages/crates, explicit workspace manifests.
   - Shared infra (`event-bus`, `storage`, `telemetry`, `types`, `ui-kit`) is the only cross-cutting layer.

## 3. Guardrails — what we do NOT do

1. **No "just a chat app" pivot**
   - No generic web-only chat experience as the main product.
   - Any chat UI is a skin on top of the full companion stack.

2. **No collapsing layers**
   - L5 does not implement routing or persona logic.
   - L1 does not implement presence or UI concerns.
   - L2 does not silently become "the app database."
   - Any proposal to merge responsibilities must go through a new decision-lock pass.

3. **No uncontrolled remote dependence**
   - The system must remain useful in degraded or offline modes.
   - Avoid designs that assume constant cloud connectivity for core functions.

4. **No policy afterthoughts**
   - New capabilities and tools must pass through L5 contracts and events.
   - "We'll add policy later" is not acceptable for any engine that can affect user data, cost, or external systems.

5. **No ad-hoc cross-package dependencies**
   - Packages depend only along approved directions (documented in lint rules).
   - If you need a type from another layer and the dependency is forbidden, you add or adjust an explicit contract — not "just import it."

## 4. Architecture guardrails

1. **Direction of dependencies**
   - Engines depend on shared infra and well-defined contracts — not on each other's internal modules.
   - L4 may depend on L5 contracts, not the other way around.
   - L6 outputs feed into L1/L3/L4 but do not import their internals.
   - L7 integrates with L5/L2 via explicit bridges.

2. **Contracts over convenience**
   - Events, requests, and responses go through types defined in interface packs.
   - If reality diverges, update the interface pack and note it in a wave report.

3. **Monorepo discipline**
   - All engines live under `packages/` with clear names.
   - Shared infra lives under `packages/` as well, never in ad-hoc utility directories.
   - Tools and governance live under `tools/` and `.github/`, not spread across engine packages.

## 5. Execution guardrails

1. **Waves, not thrash**
   - Major changes ship as named "Waves" (Wave 0, Wave 1, Wave 2, ...).
   - Each Wave has an execution report (`WAVEN_EXECUTION_REPORT_YYYY-MM-DD.md`) and an updated roadmap.

2. **Scaffold before logic**
   - First create load-bearing package shells and contracts.
   - Then implement thin, testable logic slices.
   - Only then scale out features.

3. **Always leave a roadmap graphic behind**
   - At the end of each long-run session, update the roadmap graphic to show:
     - doctrine/design status,
     - wave status,
     - engine stub and logic status,
     - productization status.

4. **Explicit drift checks**
   Each Wave report must answer:
   - "Did this Wave change the vision or guardrails?"
   - If yes, why is the change justified and what was updated in this file/planning docs?

## 6. Change control for vision & guardrails

- This file is **the single source of truth** for high-level vision and guardrails.
- Changes here require:
  - an explicit entry in a `DECISION_LOCK_PASS_*.md`, and
  - a note in the corresponding Wave execution report.
- If a Wave discovers that the current vision is impossible or clearly wrong, the correction must be deliberate and documented, not implicit.

---

## Cross-references

- [01 — Product doctrine](01_product_doctrine.md) — must remain consistent with this file; conflicts resolve in favor of this file.
- [planning/monorepo_plan_draft.md](planning/monorepo_plan_draft.md) — concrete repo layout embodying guardrail §3.5 and §4.3.
- [DECISION_LOCK_PASS_2026-04-18c.md](DECISION_LOCK_PASS_2026-04-18c.md) — five control-plane decisions implementing guardrail §3.4 and §4.1.
- [CLAUDE.md](../CLAUDE.md) — repo-level AI agent ops rules that operationalize §4 and §5.
