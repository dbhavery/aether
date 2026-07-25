# Acceptance criteria — style guide

> **Status:** Current. Closes spec-package audit Gap #6.
> **Created:** 2026-05-18.
> **Scope:** How acceptance criteria (AC) are written across the
> Companion spec package — architecture docs under `docs/` (see
> `ARCHITECTURE.md` and `docs/PRODUCT-PLAN.md`) and per-step
> execution reports.
> **Companion to:** `docs/GLOSSARY.md` §6 (rot guards vs AC).

---

## 1. What an acceptance criterion is

An **acceptance criterion** is a behavioural, testable statement
that lets a reviewer decide pass/fail by inspecting the running
system or its artefacts.

It is **not**:

- A **requirement.** Requirements describe *what the system shall
  do*. AC describe *how we verify it under inputs*.
- A **test.** Tests evaluate AC. One AC may be covered by several
  tests; one test may cover several AC. AC live in specs; tests
  live in code.
- A **rot guard.** Rot guards lock anchor strings between docs and
  code. They catch doc drift but never evaluate behaviour. See
  `docs/GLOSSARY.md` §6.
- A **hard constraint.** Hard constraints are rot-guarded
  invariants ("must stay true"). AC describe what must be true
  under specific inputs.

---

## 2. Writing rules

1. **One observable outcome per criterion.** No hidden conjunctions
   ("emits X *and also* writes Y"). Split.
2. **Active voice, user-perspective verbs.** "The user sees…", "the
   agent emits…", "the audit log shows…" — not "the function
   returns…". The spec is contract, not implementation.
3. **Testable without further interpretation.** A reviewer must
   decide pass/fail by inspection. If the AC needs a tiebreaker
   conversation, rewrite it.
4. **Every "must" implies a falsifier.** "X must happen" carries an
   implicit "else FAIL because [reason]." If you cannot state the
   falsifier, the AC is aspiration, not acceptance.
5. **Numbers carry a measurement protocol.** "p95 <150 ms" only
   counts if the AC points at the measurement (load profile,
   window, instrumentation source).
6. **No implementation guidance.** No data structures, function
   names, libraries, or file paths. AC describe externally
   observable behaviour.

---

## 3. Format

AC live under an `## Acceptance criteria` heading as a Markdown
list. Each item is one sentence (occasionally two for context).

Optional annotations:

- `(P0)` / `(P1)` / `(P2)` — priority. P0 blocks ship; P2 is
  nice-to-have.
- `(verified by: <test name | rot-guard anchor | eval scenario>)` —
  provenance hint. Helps the reviewer find the verifier.

Example heading + items:

```markdown
## Acceptance criteria

1. The user sees a "Forget" affordance on every durable memory row.
   (P0) (verified by: `memory_tab.spec.tsx::forget_visible`)
2. After "Forget", the row is absent from the next `memory_list`
   response. (P0) (verified by: `forget_propagates` integration test)
```

---

## 4. What AC are NOT

- **Implementation guidance.** ("Use a `BTreeMap` for the index.")
  → Belongs in design notes or ADRs.
- **Code style or quality rules.** ("Functions must be ≤40 lines.")
  → Belongs in `CLAUDE.md` or a lint config.
- **Performance numbers without a measurement protocol.** ("Fast.")
  → Either add the protocol or drop the criterion.
- **Restated hard constraints.** A hard constraint already lives
  in the architecture doc's "Hard constraints" section and is rot-
  guarded. Do not duplicate it as an AC; reference it.

---

## 5. Examples

### Good

1. The audit log shows one `policy_decision` row for every
   `action_request` emitted in the same session. (P0)
2. After a 30-second network drop, sync converges within 30 s of
   reconnection without losing provenance on any durable row.
   (P1) (verified by: `sync_drop_30s` integration test)
3. The Trust drawer "History" tab renders the last presence
   transition within 200 ms of the transition event. (P1)

### Bad — and why

1. ~~"The system should be reliable."~~ — Not testable; no
   falsifier; no measurement.
2. ~~"`MemoryStore::forget` returns `Ok(())` and the cache is
   invalidated."~~ — Implementation phrasing (function name,
   return type) and a hidden conjunction. Rewrite as a
   user-observable outcome and split.
3. ~~"Latency must be low."~~ — No number, no measurement protocol,
   no falsifier.

---

## 6. Maintenance

- When implementation changes a criterion's truth, update the AC
  in the same PR. Stale AC are bugs in the spec.
- Rot guards do **not** validate AC — they only lock anchor
  strings between docs and code. An AC can pass its rot-guard
  anchor check while being behaviourally false. Tests and evals
  are the verifiers; AC are the contract those verifiers implement.
- When an AC is dropped, leave a `~~struck~~` line with a
  one-sentence reason in the same commit. Silent removal hides
  spec history.
