# Handoff — 2026-04-24 Milestone 2 planning

**Written:** 2026-04-24 planning session end.
**Branch:** `dev`. Tip `ad31f5d` at session start → (this commit) at
session end. Push planned at end of session
(roadmap-complete + milestone-plan-ready per Milestone 1
retrospective §4 + Milestone 2 roadmap doctrine).
**Working tree:** clean after this handoff commit.

**Session type:** planning only. No source-code commits. Three
markdown artifacts + this handoff.

---

## 1. Commit table

| SHA | Subject |
| --- | --- |
| (this commit) | docs: open Milestone 2 — retrospective + roadmap + Run 1 prompt |

One commit covers all four files.

---

## 2. Artifacts produced

| File | Purpose |
| --- | --- |
| file:///C:/Users/dbhav/Projects/aether/MILESTONE_1_RETROSPECTIVE_2026-04-23.md | Retrospective closing the six-run roadmap 2026-04-23. |
| file:///C:/Users/dbhav/Projects/aether/ROADMAP_2026-04-24_MILESTONE_2.md | Six-run Milestone 2 roadmap. Theme: "Aether becomes retrieval-aware and user-facing." |
| file:///C:/Users/dbhav/Projects/aether/NEXT_SESSION_PROMPT_M2_RUN_1.md | Paste-verbatim prompt for Milestone 2 Run 1 (Retrieval Wiring + hygiene chore). |
| file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-24_MILESTONE_2_PLAN.md | This file. |

---

## 3. Check matrix (planning session — docs-only scope)

| Check | Result |
| --- | --- |
| `git status` | clean after commit |
| Commits ahead of `origin/dev` | 1 (this commit); push planned at session end |
| `cargo` / `pnpm` checks | not rerun — no source code touched |

Planning session; no code changed. Rot guards inherit pass state
from Run 5 (`ad31f5d`).

---

## 4. Post-session state

- **Milestone 1** — CLOSED. Retrospective written. Six-run
  roadmap (`ROADMAP_2026-04-23_SIX_RUN_PLAN.md`) fully executed.
- **Milestone 2** — OPEN. Six-run roadmap proposed. Theme:
  retrieval-aware + user-facing. Base ordering + pragmatic
  variant documented.
- **All five subsystems** — still CLOSED, rot-guarded. No
  state change this session.
- **Embeddings** — still opt-in, still unverified on real
  workloads. Milestone 2 Run 1 wires the consumer; Run 3 makes
  the opt-in frictionless.

---

## 5. Retired risks (Milestone 1 close → Milestone 2 open)

The following risks from the Milestone 1 run handoffs retire with
milestone close:

- **(RETIRED) RUN_5 Risk A — "Roadmap complete, next session needs
  a plan."** Plan exists. Milestone 2 Run 1 prompt ready.
- **(RETIRED) RUN_5 Risk B — "Backlog items ripened during
  Milestone 1."** Backlog items absorbed into Milestone 2 roadmap
  (5.5a → Run 2, retrieval wiring → Run 1, Spec gaps → Run 4,
  `pnpm eval` → Run 5, Memory tab polish → Run 6).
- **(CARRIED) RUN_5 Risk C — Ollama embedding provider unverified.**
  Milestone 2 Run 1 exposes it in router tests; Run 3 onboarding
  makes the first user-pull natural. Expect retirement in Run 3.
- **(CARRIED) RUN_5 Risk D — Flat-file embedding store rewrites on
  every mutation.** Not a blocker at personal scale. Revisit if
  Run 2's domain-typed durable store changes storage assumptions.
- **(CARRIED) RUN_5 Risk E — Shell compiles embeddings even when
  disabled.** Compliance-doc note only; no runtime impact. No
  Milestone 2 run changes this.

Additional Milestone 1 retrospective findings carrying into
Milestone 2:

- **Milestone 1 retrospective §3 item 1** — `current_status.sh`
  reads frozen-in-time handoff. **Scheduled for retirement in
  Milestone 2 Run 1's hygiene chore.**
- **Milestone 1 retrospective §3 item 2** — LF/CRLF warnings.
  **Scheduled for retirement in Milestone 2 Run 1's hygiene chore.**
- **Milestone 1 retrospective §3 item 3** — push pile / push
  cadence. Milestone 2 doctrine explicitly makes "push after
  every run" the default (roadmap "Hard constraints" section).

---

## 6. Decisions log — no additions this session

Milestone 1 closes with 70 decisions (#1–#70). Milestone 2 runs
introduce new decisions prefixed `#M2-NN` to keep them clearly
labelled. Eight Milestone 2 reserved decisions proposed in the
roadmap:

- **#M2-01** — Capability name for retrieval-augmented reads
  (Run 1 reserved).
- **#M2-02** — Retrieval timing (block vs. parallel-with-timeout)
  (Run 1 reserved).
- **#M2-03** — Union/rank strategy for embedding + session
  results (Run 1 reserved).
- **#M2-04** — Durable store shape, ADR-0003 (Run 2 reserved).
- **#M2-05** — Whether Facts / Preferences domains ship in Run 2
  (Run 2 reserved).
- **#M2-06** — Gap #3 (requirement IDs) authorisation (Run 4
  Don-only).
- **#M2-07** — ADR-0004 CI scope (Run 5 reserved).
- **#M2-08** — CI blocking vs. informational (Run 5 reserved).

All eight are proposed-only. None silently decided this session.

---

## 7. Invariants promoted to doctrine (Milestone 1 retrospective §4)

- Every subsystem gets a rot guard before it claims "Current".
  Five-for-five in Milestone 1.
- ADRs precede cross-layer refactors. Any PR touching two or
  more `packages/l*-*/` crates cites an ADR (existing or new).
- Handoffs carry a retired-risks section. This handoff complies.

Milestone 2's ADR-0003 (Run 2) + ADR-0004 (Run 5) are the next
examples of the ADR doctrine in action.

---

## 8. Hard constraints respected this session

- No source-code commits. Three markdown artifacts + this handoff.
- No reopened Milestone 1 decisions. The 70-item log carries
  forward intact.
- No new ADRs — ADRs land inside the runs that need them
  (Run 2 → ADR-0003; Run 5 → ADR-0004).
- Doctrine rules unchanged.
- Milestone 2 decisions clearly prefixed `#M2-` to avoid merge
  collision with the `#N` series.

---

## 9. Paste-verbatim reminder for next session

The Milestone 2 Run 1 starter prompt is in:

file:///C:/Users/dbhav/Projects/aether/NEXT_SESSION_PROMPT_M2_RUN_1.md

Open that file, copy the fenced ````md ... ```` block, paste into
the next session. Run 1 is retrieval wiring + the bundled hygiene
chore (`.gitattributes` + `current_status.sh` newest-handoff fix).

---

## 10. Session-end gate

- [x] Three markdown artifacts written + this handoff.
- [x] Clean working tree post-commit (pending commit).
- [x] Retired-risks section present.
- [x] Paste-verbatim reminder present.
- [ ] `git push origin dev` at session end.

---

(end of handoff)
