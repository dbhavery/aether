# Six-run roadmap — 2026-04-23

**Scope:** six named sessions from "truth + push" through Memory V2 close-out.
**Ordering principle:** stabilise truth first, remove dependency blockers
second, close documentation drift third, reopen large memory work only once
the backbone is coherent. Front-loading high-impact dependencies and drift
keeps later work compounding cleanly instead of amplifying hidden
mismatches.

---

## Run 0 — Truth & Push

**Owner:** Don.
**Type:** ≤30 min manual actions; no coding agent needed.

1. Run `./scripts/current_status.sh` (or `python scripts/current_status.py`).
   Confirms repo + handoff agree before anything else touches code.
2. `git push` the 37+ unreviewed commits. Lowers operational risk before
   Run 1 expands the branch further.
3. Record the **L2/shell `MemoryDomain` enum reconciliation** decision in
   a short note alongside the next-session prompt. Three options in
   `HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md` §4 Risk C:
     - Option 1: replace L2 enum with the design-doc enum; migrate `MemoryItem`.
     - Option 2: keep both enums; explicit mapping at the boundary.
     - Option 3: retire the L2 kernel stub; shell talks to `SessionMemoryStore`
       + a future domain-typed durable store.
   My current recommendation is Option 1 (cleanest, lowest long-term tax,
   migration is cheap because the old enum has zero consumers). But the
   call is yours — the rest of this roadmap's Memory work hangs off it.

**Gate:** Runs 2–4 cannot proceed without #3.

---

## Run 1 — QE Current

**Target:** Quality-Eval Tier 2B — close the documentation drift on the
subsystem that has moved fastest.

**Scope:**
- Add `tools/lint-quality-doc/check.py`, mirroring the pattern of
  `tools/lint-presence-doc/check.py` (commit `37f00fa`).
- Seed anchor manifest covering the QE v1.1 / v1.2 / v1.3 surface —
  symbols, strings, files. Include session-log importer symbols.
- Flip `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` from "Design-only as of
  2026-05-14" to "Current as of 2026-04-23". Reconcile any design-vs-code
  drift surfaced by anchor seeding.

**Out of scope:**
- `pnpm eval` regression harness wiring (separate, larger scope).
- Any feature work.
- Any new Tauri commands.

**Done when:** new lint script passes, doc status flipped, architecture
text matches implementation, full check matrix still green.

**Commit cadence:** 2–3 scoped commits max. Target: rot guard → anchor
seed → doc flip + reconcile.

---

## Run 2 — Memory Sweep

**Target:** Memory V2 step 5 — retention sweep.

**Precondition:** enum decision from Run 0 is locked.

**Scope (shaped by the enum decision):**
- Implement the retention sweep per `docs/MEMORY-V2-ARCHITECTURE.md` §10
  item 5: boot-time pass + low-rate background tick.
- Emit `memory_forgotten` telemetry + L5 audit rows for sweep evictions.
- Respect per-domain retention from `memory.json`
  (`retention_days: null` means "keep until forgotten").
- **Do not** start embeddings in the same run.

**Out of scope:**
- Embeddings (that is Run 3).
- Rot guard + doc flip (that is Run 4).

**Done when:** sweep runs at boot + on schedule; telemetry + audit land
correctly; tests cover both retention-ms and row-cap paths; the enum
reconciliation chosen in Run 0 is the only one present in the codebase
after the run.

**Commit cadence:** 3–4 scoped slices, depending on the enum option.

---

## Run 3 — Memory Retrieval

**Target:** Memory V2 step 6 — embeddings (opt-in) + retrieval-adjacent
behavior downstream of step 5.

**Scope:**
- Behind an explicit feature flag, per doc §8 (6). Default off.
- Local-only default embedding provider (Ollama's embedding model is the
  planned reference candidate per doc §9).
- Vector index backend decided at implementation time (sqlite-vec is one
  candidate; the doc explicitly says "decide at implementation time").
- Persist embeddings only for Durable / Projects / Artifacts on opt-in.

**Out of scope:**
- Step 7 rot guard (Run 4 only).
- Remote embedding providers.
- Any UI changes beyond a single Settings toggle (if needed at all).

**Done when:** embeddings can be enabled, an item writes produce an
embedding row, retrieval is wired to use them when available, flag-off
path is indistinguishable from today's behavior.

---

## Run 4 — Memory Lock

**Target:** Memory V2 step 7 — rot guard + doc flip. Mirrors the pattern
already used for Vision / Voice / Presence.

**Scope:**
- `tools/lint-memory-doc/check.py` with a seeded anchor manifest.
- Flip `docs/MEMORY-V2-ARCHITECTURE.md` from "Design-only" to
  "Current as of <date>".
- Reconcile implementation, docs, and telemetry names in one commit
  window so drift can't sneak back in.
- Close the Memory V2 subsystem in the same sense as Presence V1 is
  closed today.

**Out of scope:**
- Any new feature. This is purely the guard + lock.

**Done when:** fourth rot guard is live, doc is flipped, subsystem
qualifies as "closed" in future handoffs' Subsystem Status sections.

---

## Run 5 — Polish & IDs

**Target:** exactly ONE of the following three. Not more.

- **Option A: MemoryDrawer vs MemoryTab consolidation.** Either retarget
  the header Memory button to open the Trust drawer on the Memory tab,
  or delete `MemoryDrawer.tsx` + button. Tiny, ~15 min if scoped tightly.
- **Option B: `pnpm eval` harness wiring.** Downstream of session-log
  importer + QE rot guard. Adds a scripted eval run to the package.json
  test ladder.
- **Option C: Forward-looking requirement IDs (Gap #3).** Short design
  doc keyed to `docs/GLOSSARY.md` §11, with one concrete ID per existing
  architecture doc. Don-reserved per prior handoff.

**Discipline:** do NOT bundle two. Small, single-purpose runs stay
reviewable.

---

## Path map (compressed)

| Run | Name | Target | Precondition |
| --- | --- | --- | --- |
| 0 | Truth & Push | Status, push, enum call | none |
| 1 | QE Current | Quality-Eval Tier 2B | Run 0 |
| 2 | Memory Sweep | Memory V2 step 5 | enum call locked |
| 3 | Memory Retrieval | Memory V2 step 6 | Run 2 |
| 4 | Memory Lock | Memory V2 step 7 + rot guard | Run 3 |
| 5 | Polish & IDs | Pick ONE cleanup | Run 4 (or parallel after 1) |

---

## Pragmatic variant (if you want Memory momentum over doc tidiness)

Swap Runs 1 and 2. Order becomes:

- Run 0: Truth & Push (unchanged).
- Run 1: Memory Sweep (was Run 2).
- Run 2: QE Current (was Run 1).
- Run 3: Memory Retrieval.
- Run 4: Memory Lock.
- Run 5: Polish & IDs.

My recommendation stays with the base ordering (QE first) unless you
lock the enum call immediately and want all Memory work contiguous —
closing QE doc drift sooner pays back quickly as session count rises.

---

## Gate conditions (do not skip)

- **Run 2+ requires the enum call.** If Run 0 didn't lock it, park Memory
  work and cycle Run 1 + Run 5 variants instead.
- **Run 4 requires Run 3 to actually behave.** The doc flip should
  describe implementation, not aspirations.
- **Push discipline:** authorise a push at the end of each run, not just
  end-of-day. The 37-commit pile is a signal; don't let it re-accumulate.

---

(end of roadmap)
