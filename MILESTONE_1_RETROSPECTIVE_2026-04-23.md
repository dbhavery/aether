# Milestone 1 — Retrospective (2026-04-23)

**Written:** 2026-04-23 Milestone 2 planning session.
**Scope closed:** six-run roadmap 2026-04-23 + the all-nighter setup session that preceded it.
**Tip at close:** `ad31f5d` (Run 5 — MemoryDrawer consolidation).

---

## 1. Scope recap

- **Six runs shipped.** Run 0 (truth/push) → Run 1 (QE Tier 2B) → Run 2 (Memory V2 step 5, retention sweep + ADR-0001 execution) → Run 3 (step 6, embeddings) → Run 4 (step 7, rot guard + doc flip) → Run 5 (MemoryDrawer retired).
- **Five subsystems rot-guarded.** Vision V1, Voice V1, Presence V1 entered the milestone already closed; **Memory V2 and Quality-Eval V1 closed during it**. Every closed subsystem now has a `tools/lint-<name>-doc/` anchor lint gating doc drift.
- **Two ADRs accepted + executed.**
  - ADR-0001 — `MemoryDomain` reconciliation (Option 3: retire L2 kernel stub; L2 owns canonical enum). Executed in `ef13b0e`.
  - ADR-0002 — embeddings provider + vector backend (Ollama `nomic-embed-text` default, flat-file domain-partitioned store, `MemoryEmbed` capability). Executed in `e135c2a`.
- **Test growth.** Shell: 198 → 210 tests (+12). L2: +12 embedding + 6 sweep tests. Frontend: 169 → 188 tests (+19), then -3 module on Run 5 consolidation. Parallel-test flakes retired earlier in the milestone remain retired.
- **Net frontend shrink.** 64 → 63 modules (`MemoryDrawer.tsx` deleted); bundle 237→235 kB.
- **70 numbered decisions carried.** Zero re-opened silently. Reserved decisions honoured (requirement IDs, `git push`, etc.).

Commit anchors worth remembering:
- `f357d56` — `current_status.sh` kills stale-prompt pattern.
- `b538dd9` — ADR-0001.
- `ef13b0e` — ADR-0001 execution.
- `a1e9028` — retention sweep.
- `e135c2a` — embeddings.
- `120b6d0` — Memory V2 doc flip + rot guard.
- `4b0a5ce` — QE doc flip + rot guard.
- `ad31f5d` — Run 5 consolidation.

---

## 2. Patterns that worked

1. **ADR-before-code.** ADR-0001 unblocked Run 2; ADR-0002 unblocked Run 3. Both landed mechanically once the ADR was accepted — no mid-implementation design wobble. Cost: one extra commit per structural decision. Payoff: zero rework, one trustworthy source of "why" per structural change.
2. **Rot-guard-in-the-same-commit-window as the doc flip.** Run 1 Tier 2B (`4b0a5ce`) and Run 4 Memory Lock (`120b6d0`) both shipped the lint + the "Current" status change together. No subsystem doc has been allowed to sit in "Current" state without a guard since Presence. Pattern: `feat(tools): lint-<name>-doc ... + flip ... to Current`.
3. **Bundle-when-natural.** Runs 1+2 and Runs 3+4 landed in single long sessions because each pair shared a verification surface and the second phase was gated on the first. Run 5 was deliberately solo because its scope (frontend polish) had no cargo dependency on the prior phases. Bundling was a choice, not an ambush.
4. **Retired-risks sections in every handoff.** Once a risk was retired (e.g. Risk A "enum mismatch" after ADR-0001 executed), it was labelled `(RETIRED)` in the next handoff's §4. Stale risks did not travel forward.
5. **Repo-beats-prompt (Decision #32).** Flagged in-flight in Run 1+2 §6 when `current_status.sh` surfaced a stale Risk A from the 2026-05-18 handoff. Stale prompt was not obeyed; repo truth won.

## 3. Patterns to fix

1. **`current_status.sh` reads a frozen-in-time handoff.** Confirmed again this session — the script still surfaced stale Risk A after ADR-0001 retired it. Two possible fixes: (a) script picks the newest `HANDOFF_*.md` by filename date; or (b) live-truth leaves the handoff entirely (a persistent `STATUS.md` updated on each run's commit). Either kills the class of bug.
2. **LF/CRLF line-ending warnings on every commit.** Pure noise, but it trains graders of commits to ignore warnings. A one-line `.gitattributes` (`* text=auto eol=lf`) silences it permanently.
3. **Push pile.** Roadmap Run 0 intended the push before Run 1. That gate was deferred — the branch was 40 commits ahead at one point. Push at the end of each run (not at session end) is a discipline the roadmap already captured but we did not execute until the mid-session push in Run 3+4. Milestone 2 should enforce it on Run 1.

## 4. Invariants worth promoting to doctrine

These are no longer "things we happen to do" — they happened enough times to be rules.

1. **Every subsystem gets a rot guard before it claims "Current".** Vision, Voice, Presence, Quality-Eval V1, Memory V2 — five for five. Any future subsystem that lands without a `tools/lint-<name>-doc/` counterpart should be rejected in review.
2. **ADRs precede cross-layer refactors.** Two examples (0001, 0002). Propose making this a policy: any PR touching two or more `packages/l*-*/` crates cites an ADR (existing or new). Single-layer work does not need one.
3. **Handoffs carry a retired-risks section.** Stops risk-inertia between sessions. Format already stable; promote to template.

## 5. What this buys Milestone 2

- **Five closed subsystems = five places where doc + code + lint agree.** Memory V2 retrieval wiring has a stable surface to plug into.
- **Embeddings trait is live and proven opt-in.** Runtime flag works; provider failure is best-effort warn, not a blocker. Ready for retrieval to consume.
- **ADR mechanics are warm.** Any Milestone 2 run that needs a structural call (domain-typed durable store, retrieval failure semantics, CI design) can reach for the ADR habit without ceremony.
- **Decision count (70) is the guardrail**, not a burden. Reserved decisions held; the next milestone inherits a branch where you know every cross-cutting call has a number and a rationale.

---

(end of retrospective)
