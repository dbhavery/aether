# Handoff — 2026-04-23 planning session (ADR-0001 + six-run roadmap)

**Written:** 2026-04-23 end-of-session.
**Branch:** `dev`. Commits ahead of `origin/dev` at session end depends on
whether Run 0's push was authorised; run `./scripts/current_status.sh`
for the live count.
**Working tree:** clean after this handoff lands.

This was a **planning session**, not an implementation session. No
production code changed. Three durable artifacts shipped: the
six-run roadmap, ADR-0001 (MemoryDomain reconciliation), and this
handoff.

---

## 1. What shipped in this session

| SHA | Subject |
| --- | --- |
| TBC at commit time | docs(roadmap): add six-run roadmap 2026-04-23 |
| TBC at commit time | docs(adr): add ADR-0001 — MemoryDomain enum reconciliation (retire L2 kernel stub) |
| TBC at commit time | docs: 2026-04-23 session handoff — ADR-0001 + six-run roadmap |

Three moves:

- **Roadmap written.** `ROADMAP_2026-04-23_SIX_RUN_PLAN.md` sequences
  the remaining Memory V2 + Quality-Eval work into six named sessions
  (Run 0 Truth & Push → Run 1 QE Current → Run 2 Memory Sweep → Run 3
  Memory Retrieval → Run 4 Memory Lock → Run 5 Polish & IDs). Front-loads
  truth recovery and dependency decisions so implementation work
  compounds cleanly.
- **ADR-0001 accepted.** `docs/adr/ADR-0001-memory-domain-reconciliation.md`.
  Retires the L2 kernel stub (zero real-world consumers per grep);
  relocates `MemoryDomain` from `apps/desktop/src-tauri/src/memory_config.rs`
  into `packages/l2-memory/src/domain.rs`; deletes `kernel.rs` with its
  unused `MemoryKernel`, `MemoryItem`, `PrivacyClass`, `RetentionKind`,
  `EmbeddingStore`, and kernel `MemoryDomain`. The six-domain shell
  taxonomy (Session / Durable / Facts / Projects / Preferences /
  Artifacts) is the single source of truth going forward. Unblocks
  Memory V2 step 5.
- **Run 0 completed** (per the roadmap):
  - Status script run; repo and handoff agreed.
  - Push decision recorded: authorised before Run 1 starts (see
    §4 Risk A below).
  - `MemoryDomain` enum decision recorded in ADR-0001.

---

## 2. Roadmap at a glance (six runs)

| Run | Name | Target | Precondition |
| --- | --- | --- | --- |
| 0 | Truth & Push | Status, push, enum decision | — |
| 1 | QE Current | Quality-Eval Tier 2B — rot guard + doc flip | Run 0 |
| 2 | Memory Sweep | Memory V2 step 5 per ADR-0001 | Run 0 (enum locked) |
| 3 | Memory Retrieval | Memory V2 step 6 — embeddings | Run 2 |
| 4 | Memory Lock | Memory V2 step 7 — rot guard + doc flip | Run 3 |
| 5 | Polish & IDs | ONE of: drawer-tab consolidation · pnpm eval · requirement IDs | Run 4 (or parallel after Run 1) |

Full rationale, scope, and "done when" criteria in
`ROADMAP_2026-04-23_SIX_RUN_PLAN.md`.

**The next session is a multi-phase bundle of Run 1 + Run 2** — both
are now unblocked, both benefit from landing in the same session
(QE rot guard is trivially verifiable; Memory step 5 has a clean
committed reference in ADR-0001). Starter prompt:
`NEXT_SESSION_PROMPT_2026-04-23_RUN_1_PLUS_2.md`.

---

## 3. Subsystem status (unchanged from 2026-05-18 handoff)

- **Vision V1** — closed, rot-guarded.
- **Voice V1** — closed, rot-guarded.
- **Presence V1** — closed, rot-guarded.
- **Memory V2** — steps 1–4 complete. **Step 5 NOW UNBLOCKED** by
  ADR-0001. Steps 6–7 pending, downstream of 5.
- **Quality-Eval V1** — v1.3 complete. Tier 2B (rot guard + doc flip)
  is Run 1 primary.
- **Spec package** — glossary + NFR skeleton in; gaps #3–#6 pending.
- **Test infrastructure** — parallel-test flakes retired 2026-05-18;
  default `cargo test` parallelism is safe.

---

## 4. Risks / alerts for the next session

### A. Push authorisation is Run 0's final act

The push decision is now explicit per the roadmap: **authorise the
push before Run 1 starts**. 37+ commits ahead is growing into genuine
merge-conflict exposure. Don — do the `git push origin dev` yourself
(reserved decision) before handing the next session to the agent, or
record a time-bounded "hold until <condition>" reason in this
handoff's decisions log.

### B. ADR-0001's relocation step is a cross-layer change

Moving `MemoryDomain` from shell to L2 is formally a two-package
change: `packages/l2-memory` (add `domain.rs`, delete `kernel.rs`,
trim `lib.rs`) + `apps/desktop/src-tauri` (delete local enum, import
from L2). This is within Run 2's scope per ADR-0001, but it does
cross the "one layer per session" guideline in `CLAUDE.md` §1.3.
The ADR itself is the coordinator-level authorisation; the next
agent can proceed without asking again.

### C. `EmbeddingStore` deletion is irreversible

ADR-0001 deletes the Wave 4 `EmbeddingStore` trait along with the
rest of `kernel.rs`. Run 3 (Memory Retrieval) will reintroduce an
embedding trait from scratch — probably under `embeddings.rs` with
a shape informed by whatever local embedding provider we pick
(Ollama embedding model is the design-doc candidate). If Don has
a strong preference for preserving the exact old trait shape, say
so before Run 2 lands; otherwise Run 3 has a clean slate.

### D. Gemma 4 still unverified on real workloads

Unchanged. No `ollama pull gemma4` + `--backend ollama` run has
happened. Narrow rollback path if needed.

### E. `MemoryDrawer` / `MemoryTab` coexistence

Unchanged. Deferred to Run 5 Option A.

### F. 2026-05-18 handoff's subsystem-status section reports "34 commits ahead"

Minor drift in that doc — the real count at end-of-session was 37,
and the status script surfaces live count separately. No action
needed; noting for history.

---

## 5. What's on deck for the next session

### Multi-phase bundle: Run 1 + Run 2

Full scope in `NEXT_SESSION_PROMPT_2026-04-23_RUN_1_PLUS_2.md`.
Summary:

**Phase 1 — Run 1 — Quality-Eval Tier 2B.**
`tools/lint-quality-doc/check.py` mirroring `tools/lint-presence-doc/`.
Anchor manifest covers v1.1 / v1.2 / v1.3 symbols. Flip
`docs/QUALITY-EVAL-V1-ARCHITECTURE.md` status from "design-only"
to "current". Reconcile design-vs-code drift surfaced by anchor
seeding.

**Phase 2 — Run 2 — Memory V2 step 5 per ADR-0001.**
Two sub-phases:
1. **ADR-0001 execution:** relocate `MemoryDomain` to
   `packages/l2-memory/src/domain.rs`; delete `kernel.rs`;
   trim `lib.rs`; update shell import.
2. **Retention sweep:** boot-time pass + low-rate background tick
   per `docs/MEMORY-V2-ARCHITECTURE.md` §10 item 5. Emits
   `memory_forgotten` telemetry + L5 audit rows on sweep eviction.
   Respects per-domain retention from `memory.json`. Tests for
   both TTL and row-cap paths.

**Tier 3 — optional cleanup.** ONE of: flake-harness regression
check (re-prove 2026-05-18 fixes), `scripts/current_status.sh`
hardening, or a skip. Do not bundle.

### Out of scope

- Memory V2 step 6 (embeddings) — Run 3, not this session.
- Memory V2 step 7 (rot guard) — Run 4.
- Any new `packages/*/` or `apps/*/` directory.
- `git push` — handled by Don before the session starts (or
  deferred explicitly).
- Any doctrine refresh.

---

## 6. Decisions log (new this session — #52)

- **52. ADR-0001 — MemoryDomain enum reconciliation accepted.**
  Retire the L2 kernel stub; relocate `MemoryDomain` to L2 as the
  only shared taxonomy; `SessionMemoryStore` (and future
  domain-typed durable store) becomes the only shared storage
  contract. Full reasoning and consequences in
  `docs/adr/ADR-0001-memory-domain-reconciliation.md`. Unblocks
  Memory V2 steps 5–7.

Carried: 1–51 from prior handoffs.

---

## 7. Next recommended prompt

Full prompt lives in
`NEXT_SESSION_PROMPT_2026-04-23_RUN_1_PLUS_2.md`. Paste that file
verbatim when starting the next session. It opens with the
mandatory `./scripts/current_status.sh` step and pins scope to
Run 1 + Run 2 with hard guardrails against Tier-3 drift.

---

(end of handoff)
