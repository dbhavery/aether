---
status: working
date: 2026-04-18
owner: Don (human coordinator)
---

# 00 — Orchestration Map

Authoritative coordination artifact for the Aether planning + build phase. Defines the operating model, agent roster, ownership matrix, dependencies, checkpoints, human decision gates, conflict-escalation protocol, and the two doctrine reconciliations (Tauri vs pywebview; 7-vs-8 layer count) locked this session.

---

## 1. Layer-model reconciliation (7 vs 8)

- **Canonical doctrine** ([01_product_doctrine.md](../01_product_doctrine.md) §"Must-own layers") currently enumerates **8** must-own layers: presence controller, memory kernel, model router, reflex router / interaction state machine, policy/authorization engine, persona compiler, latency-aware social timing system, onboarding/trust UX.
- **This session's planning** uses **7 layers** (L1–L7), folding the reflex router into L1 Interaction Timing rather than tracking it as a separate planning layer. The inbox Pro roadmap, all layer plans, the Pro-phase crosswalk, and the OSS alignment map already converge on 7.
- **Decision (locked, [DECIDED 2026-04-18] in `OPEN_QUESTIONS.md`):** The **7-layer model is the working truth.** Canonical doctrine will be updated in the next pass to reflect the 7-layer split while preserving reflex as a distinct concept inside L1.
- **Reflex is not demoted.** It remains an explicit sub-system of L1 — called out in L1's scope, tested against L1's acceptance criteria, and tracked in L1's P0–P4 sequencing. What changes is the planning cardinality (7 agents, not 8), not the moat surface count.

This reconciliation is recorded before any other orchestration content so the conflict cannot be hidden or silently re-opened.

---

## 2. Tauri vs pywebview reconciliation

- **UI technology default:** HTML / CSS / JS, shared across the Aether family.
- **Desktop shell doctrine:** **Tauri is the long-term default** for all Aether-family products.
- **pywebview status:** tactical, OSS-Preview-only shortcut if speed-to-demo absolutely requires it. Explicitly **non-doctrinal**. Must be marked preview-only wherever referenced.
- **What the old memory note (`feedback_css_default_for_ui.md`, 2026-04-11) preserved:** "Never Tkinter/Qt for visual UI; use web tech." Fully retained — Tauri is web tech behind a native Rust shell.
- **What the old note superseded:** its framework specificity (pywebview only). For the Aether family's long-term foundation, Tauri supersedes.

Any agent citing the old memory note as "pywebview is canonical" is wrong and must flag the conflict.

---

## 3. Operating model

- **Human coordinator:** Don. Resolves doctrine, locks decisions, accepts agent outputs.
- **Agents:** self-contained briefing packs + task-specific one-shot prompts. **No free-running meta-agent.** No autonomous doctrine rewrites.
- **Planning interface:** canonical folder `file:///C:/Users/dbhav/Projects/aether-planning/` + locked doctrine in [01_product_doctrine.md](../01_product_doctrine.md).
- **Authority flow:** agents read canonical planning docs → execute bounded scope → report back → Don locks decisions → canonical updated.
- **No-silent-drift rule:** any doctrine-relevant conflict must be flagged and escalated. Never silently choose a side.

---

## 4. Agent roster (build phase)

### Must-own layer agents (L1–L7)

| Agent | Layer | Owns |
|---|---|---|
| L1 | Interaction timing (includes reflex) | Turn-state machine, reflex classifier, ack phrase pool, timing contracts |
| L2 | Memory kernel | Five-layer memory, retrieval, governance, sync foundations |
| L3 | Presence engine | Avatar state, viseme pipeline, rendering integration, fps-by-tier |
| L4 | Model router | Tier abstraction (fast/main/heavy), Gemma 4 routing, fallback chains, BYOK |
| L5 | Policy / authorization engine | Capability model, risk classes, autonomy presets, audit log |
| L6 | Persona / compiler system | Persona pack schema, compiler, hot-reload, provenance gate |
| L7 | Trust UX + onboarding | Wizard, trust center, permissions UX, cost visibility, guest mode |

### Cross-cutting agents (X1–X4)

| Agent | Stream | Owns |
|---|---|---|
| X1 | Repo restructure | Monorepo layout, workspace config, package boundaries |
| X2 | Isabelle migration | Phased migration plan, parallel-overlap windows, cutover gates |
| X3 | Tauri architecture | Desktop shell, WebView2 integration, Rust core boundaries, signed updater |
| X4 | v1.0 content port (one-shot) | 8-screen wizard, Guest mode, distribution playbook, cost UX, Inno scaffold |

Total: 11 agents. Realistic concurrency: 3–4.

---

## 5. Ownership matrix

Every file in `plans/`, `prompts/`, and `roadmaps/` has exactly one owner at a time. Doctrine files (`01`–`18`, `README.md`, `OPEN_QUESTIONS.md`) are coordinator-owned; agents propose edits via flagged conflicts and never rewrite doctrine directly.

| Agent | Writes to | Reads | May not modify |
|---|---|---|---|
| L1 | `plans/L1_*.md` | All `0N_*.md`, `roadmaps/*`, `17`, `18` | Doctrine, other layer plans |
| L2 | `plans/L2_*.md` | `10`, `13`, `16` | Doctrine, other layer plans |
| L3 | `plans/L3_*.md` | `11`, `14`, `01` | Doctrine, other layer plans |
| L4 | `plans/L4_*.md` | `18`, `09`, `14` | Doctrine, other layer plans |
| L5 | `plans/L5_*.md` | `12`, `13`, `08`, `01` | Doctrine, other layer plans |
| L6 | `plans/L6_*.md` | `17`, `04`, `05`, `09`, `10`, `11`, `18` | Doctrine, other layer plans |
| L7 | `plans/L7_*.md` | `05`, `06`, `07`, `12`, `13` | Doctrine, other layer plans |
| X1 | `plans/X1_*.md`, future monorepo `MIGRATION_PLAN.md` | Handoff, session summary, `16`, `03_content_lock` | Isabelle_Kunstig, any layer code, doctrine |
| X2 | `plans/X2_isabelle_inventory.md` | `isabelle_private.md`, Isabelle_Kunstig repo | Isabelle_Kunstig production data without Don |
| X3 | `plans/X3_*.md` | `16`, `15`, `03_content_lock` §5, L1–L7 | Frontend code, layer plans |
| X4 | `plans/03_content_lock_v1_port.md`, `plans/X4_port_sequence.md` | v1.0 `aether/docs/*` read-only | v1.0 repo, layer plans without coordination |

---

## 6. Dependency DAG (narrative)

- **L1** depends on L2 (memory hits <150 ms), L4 (route_decision), L5 (policy gate for tool plans).
- **L2** depends on L5 (policy-gated reads/writes), L6 (persona salience rules); informs L1 (reflex), L4 (confidence), L6 (salience feedback).
- **L3** depends on L1 (turn state), L6 (persona visual style), Media engine (visemes, tts chunks).
- **L4** depends on L2 (memory confidence), L5 (tool gate), L6 (privacy posture + compiled prompt).
- **L5** is depended on by every layer that touches tools, memory writes, or external actions.
- **L6** is depended on by L1 (phrase pool), L2 (salience rules), L3 (visual params), L4 (tier preferences), L5 (persona-scoped approval defaults), L7 (onboarding pipeline).
- **L7** depends on L5 (permissions UI), L2 (memory-review UI), L4 (routing audit UI), L6 (persona picker), L1 (first-run handoff).
- **X1** blocks *serious implementation start* (code, repo changes); does **not** block planning, content-port, or subsystem specs.
- **X2** blocks Isabelle-specific implementation in L1/L2 only; independent of other layer planning.
- **X3** blocks Pro desktop implementation; does not block planning.
- **X4** is a one-shot feeding L7 and planning docs.

---

## 7. Dependency log (table)

| Upstream | Downstream | Owner | Blocker level | Contingency if delayed |
|---|---|---|---|---|
| L5 policy schema + event contract | L1, L2, L4, L7 | L5 | hard | Layers stub policy calls behind an interface; replaced when L5 lands |
| L2 memory-hit event | L1 reflex classifier | L2 | hard | L1 uses empty-memory path until event exists |
| L6 persona compiler output | L1 phrase pools, L3 visual, L4 router bias, L5 defaults, L7 onboarding | L6 | hard | Layers use hard-coded default persona until compiler ships |
| L4 route_decision event | L1 turn-state machine | L4 | hard | L1 uses direct-to-main routing as fallback |
| L1 turn-state bus | L3 presence state | L1 | soft | L3 runs idle-loop until state bus exists |
| L7 permissions UX | L5 approval flows | L7 | soft | L5 exposes CLI/JSON surface; UX wraps later |
| Event bus (Rust, typed) | all layers P1+ | X3 / L1 jointly | hard | P0 can ship in Python/TS behind a shim |
| X1 monorepo layout | All implementation | X1 | hard (code) / info (planning) | Planning continues in current folder structure |
| X2 Isabelle capability inventory | Isabelle-specific code moves | X2 | hard (for migration) | Isabelle_Kunstig continues in place |
| X3 Tauri shell + signed updater | Pro desktop build | X3 | hard (Pro code) / info (planning) | OSS Preview may ship on pywebview as tactical exception |
| X4 v1.0 content port | L7 wizard copy, L4 cost UX, Guest-mode spec | X4 | soft | L7 uses 06_onboarding_spec 7-step until 8-screen lands |
| Rendering-surface decision (Unreal / custom GL / hybrid) | L3 Phase 2+ | Don | hard (L3 Phase 2) | L3 uses OSS Preview borrowed stack until locked |
| Sync architecture (CRDT vs op-log) | L2 Phase 5, L5 Phase 5, L7 Phase 5 | Don | hard (Phase 5) | Single-device code paths continue in Phases 0–4 |

---

## 8. Coordination checkpoints

| Gate | What must be true | Don's lock action |
|---|---|---|
| **End-of-planning (this session)** | All L1–L7 plans present; phase crosswalk + OSS alignment + content lock present; 7 decisions locked in `OPEN_QUESTIONS.md`; inbox reconciled | Sign `SESSION_END_INDEX_2026-04-18b.md` |
| **Pre-implementation** | X1, X2, X3 plans written + reviewed; monorepo `MIGRATION_PLAN.md` approved | Approve plans; authorize monorepo creation |
| **Pro Phase 0 → 1** | L1/L2/L4/L5 contracts frozen; L6 compiler I/O locked; L7 design-system foundation shipped; event bus shape agreed | Lock interfaces |
| **Pro Phase 1 → 2** | Reflex path end-to-end (Gemma 4 local); onboarding wizard complete; permission evaluator v1; persona compiler v1 | Sign Phase 1 gate |
| **Pro Phase 2 → 3** | Router v1 (local/remote); durable memory; trust center v1; ack engine + timing SLAs measured | Decide L3 rendering surface |
| **Pro Phase 3 → 4** | Presence controller v1; anti-uncanny stabilizer; rendering surface integrated; avatar-timing p95 met | Approve tool-autonomy scope |
| **Pro Phase 4 → 5** | Full 5-preset ladder; action-history replay; red-team suite v1 green; routing-decision audit UI | Decide sync architecture (CRDT vs op-log) |
| **Pro Phase 5 → 6** | Multimodal memory; mobile companion alpha; sync converges on reconnect | Approve Isabelle overlay work |

At each gate: Don reviews outputs, locks decisions, updates `OPEN_QUESTIONS.md`, and — if dependencies shift — updates this map.

---

## 9. Human decision gates

Reserved for Don, not agents:

- Rendering engine for Pro avatar (Unreal-class / custom GL / hybrid).
- Sync architecture (CRDT vs op-log).
- OSS Preview MVP cut line (which features ship in hours/days vs are teaser-only).
- ms budgets and framerate targets by performance tier.
- Final naming (Aether Pro / Core / One; Isabelle formal name).
- Hosted frontier-LLM acceptable-use rules for the deliberative path.
- Whether to rewrite `feedback_css_default_for_ui.md` memory note after Tauri lock.
- Doctrine update pass to reflect 7-layer split (pending).
- Fate of sibling `aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/` (archive / consolidate / delete).

---

## 10. Conflict-escalation protocol

When an agent encounters a conflict (doctrinal, dependency, or instruction):

1. **Stop at the conflict.** Do not silently pick a side.
2. **Flag it in the agent's session summary** with:
   - file(s) in conflict,
   - what each side says,
   - proposed minimal resolution,
   - what work can continue in parallel while Don decides.
3. **Don resolves** → update `OPEN_QUESTIONS.md` with `[DECIDED <date>]` + provenance block.
4. **Update this map** if dependencies shift.

Known conflicts already resolved this session:
- **7 vs 8 layers** — see §1.
- **Tauri vs pywebview** — see §2.
- **Inbox vs canonical roadmaps** — see [INBOX_RECONCILIATION_2026-04-18b.md](../INBOX_RECONCILIATION_2026-04-18b.md).

---

## 11. No-silent-downgrade verification

This map explicitly preserves — and any future artifact that weakens one of these without an explicit `[DECIDED]` entry in `OPEN_QUESTIONS.md` is a drift and must be reverted:

- Tauri long-term desktop doctrine.
- Per-must-own-layer primary planning axis + per-Pro-phase secondary crosswalk.
- Monorepo with strong internal boundaries.
- Don-as-coordinator operating model.
- Premium assistant/companion quality ceiling.
- No-close-enough-SaaS for must-own layers.
- 7-layer planning model (reflex inside L1).

---

## 12. "Done means" acceptance

This orchestration map is done when all of the following hold:

- [x] 7-vs-8 layer reconciliation recorded before any other orchestration content (§1).
- [x] Tauri vs pywebview reconciliation explicit (§2).
- [x] All 11 agents have defined scopes and single owners (§4, §5).
- [x] Dependencies listed both narratively (§6) and as a table (§7).
- [x] Coordination checkpoints enumerated (§8).
- [x] Human decision gates enumerated (§9).
- [x] Conflict-escalation procedure explicit (§10).
- [x] No-silent-downgrade verification list present (§11).
- [x] Every cross-cutting blocker has a named contingency (§7).
