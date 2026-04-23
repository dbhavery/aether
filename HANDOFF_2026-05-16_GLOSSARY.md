# Handoff — glossary keystone + stale-prompt correction (2026-05-16, late)

**Written:** 2026-05-16 late evening.
**Branch state:** `dev` at `a979ab7`, **18 commits ahead** of
`origin/dev`. Push **not authorized**.
**Next session mode:** Memory V2 step 3 (per-domain write/read
plumbing via the policy surface landed earlier this day).
Alternatives: `docs/NFR.md` skeleton (audit gap #2), Presence V1
step 4 (rot guard).

---

## 0. Status at end of session

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | **18** |
| `cargo fmt --all -- --check` | clean (no rust touched this session) |
| `cargo check --workspace` | clean (last green: 2026-05-16 evening) |
| `cargo test --workspace` | 149 / 149 (last green) |
| `cargo test -p aether-l3-presence` | 22 / 22 |
| `apps/desktop/src-tauri cargo test --features …` | 175 / 175 |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 pass |
| `apps/desktop && pnpm typecheck && pnpm build && pnpm test` | 145 / 145 |

No code was changed this session; only `docs/GLOSSARY.md` was added.
All prior green checks remain green.

Known flaky tests (unchanged, pre-existing):
- `state::tests::yaml_persona_pack_merges_into_catalog`
  (`AETHER_PERSONAS_DIR` contamination).
- `providers::ollama::tests::from_env_uses_defaults_when_vars_unset`
  (same env-contamination class). Both pass in isolation / under
  `--test-threads=1`.

---

## 1. What landed this session

### 1.1 `docs/GLOSSARY.md` — audit gap #1 closed

- 535-line skeleton, 11 top-level sections matching the session
  prompt's §B.2.
- Structure + stubs only (per §B.3). Most entries carry
  `TODO — derive from <source>` placeholders linking to the
  canonical architecture or planning doc.
- Load-bearing decisions encoded in the skeleton itself:
  - **Assistant posture (L3) and user attention (L3) are distinct**
    — §2 namespaces them rather than letting context do the work.
    Prevents the "presence state" ambiguity from re-leaking.
  - **Rot guards ≠ acceptance criteria** — §6 and §0.1 document the
    split explicitly. Rot guards enforce doc/code anchor presence;
    AC verify behaviour under inputs. Future docs must not collapse
    these.
  - **Canonical execution notation is `subsystem V<N> step <N>`;
    Waves 1–4 is the coarse architectural phasing; L1–L7 is a
    dependency/moat axis, NOT a time axis** — §4.
  - **Router tier vs performance tier are different axes** — §9.
    Flagged so future NFR work doesn't collapse them.
- §11 tracks four open glossary-scoped decisions for promotion if
  they survive:
  1. AC house style (bullets-with-thresholds vs Given/When/Then).
  2. Requirement ID scheme (proposed `<layer>-<subsystem>-<NNN>`).
  3. L3 sub-layer split (two controllers today; watch for a third
     axis).
  4. Cross-system spec doc shape (pointer doc vs generated view).

### 1.2 Stale-prompt correction

The session prompt listed Presence V1 step 2 as pending and asked
for Part A to implement it. Repo head `f02d4f9` (written earlier
the same day) shows that step 2, step 3, Memory V2 step 2, and
Quality-Eval v1.1 are all already complete.

Per the governance rule "if the repo contradicts the prompt,
follow the repo," Part A was **declined**. Part B (glossary)
landed. The decline is documented in the glossary commit body
so the record is explicit.

Observation worth acting on: the prompt's "high-level status"
block was written from a stale handoff. Consider a small script
`scripts/current_status.sh` that tails the newest
`HANDOFF_*.md` and prints the subsystem-status block; pipe it
into future prompt drafts.

---

## 2. Track status snapshot

Unchanged from the 2026-05-16 (evening) handoff except for the
glossary line:

- **Vision V1** — DONE, rot-guarded. Maintenance only.
- **Voice V1** — DONE (steps 1–6 + real whisper.cpp inference).
  Rot-guarded.
- **Presence V1**:
  - Step 0 (architecture) ✅
  - Step 1 (presence.json + Settings toggles) ✅
  - Step 2 (controller + OS-idle probe + events + threshold
    editing UI) ✅
  - Step 3 (Trust drawer presence-history rendering) ✅
  - Step 4 (presence rot guard) — **pending**
- **Memory V2**:
  - Step 0 (architecture) ✅
  - Step 1 (L5 additive capabilities) ✅
  - Step 2 (`memory.json` + policy surface + Settings section) ✅
  - **Step 3 (per-domain write/read plumbing) — pending, NEXT**
  - Steps 4–7 (Memory tab, sweep, embeddings, rot guard) — pending
- **Quality-Eval**:
  - v1 scaffold ✅
  - v1.1 (adversarial probes + live Ollama hook) ✅
  - Replay importer, rot guard, regression harness — pending
- **Spec package (audit-gap work)**:
  - **Glossary (gap #1) ✅ this session**
  - NFR catalogue (gap #2) — pending
  - Forward-looking requirement IDs (gap #3) — pending
  - OSS / Pro / Cross-system views (gap #4) — pending
  - Light RTM view from rot-guard manifests (gap #5) — pending
  - AC house style doc (gap #6) — pending

---

## 3. Commits (this session)

| SHA | Subject |
| --- | --- |
| `a979ab7` | docs: glossary skeleton — closes audit gap #1 |

Cumulative session run (2026-05-16, all of today):

| SHA | Subject |
| --- | --- |
| `3894ca9` | feat(l3-presence): UserAttentionController — Presence V1 step 2 (slice 1) |
| `30b77e7` | feat(apps/desktop): idle probe + poll loop + presence_status — Presence V1 step 2 (slice 2) |
| `db990ce` | feat(apps/desktop): memory.json + policy surface — Memory V2 step 2 |
| `f6a71d5` | feat(apps/desktop): Settings UI + Trust drawer presence rendering — Presence V1 step 2+3, Memory V2 step 2 UI |
| `5094fdf` | feat(tools/evals): v1.1 — live Ollama hook + per-domain adversarial probes |
| `f02d4f9` | docs: Presence V1 step 2+3, Memory V2 step 2, Quality-Eval v1.1 reports + 2026-05-16 handoff |
| `a979ab7` | docs: glossary skeleton — closes audit gap #1 |

---

## 4. Risks / things to review first

1. **18 unpushed commits.** Push still not authorized.
2. **Stale-prompt pattern.** The session prompt's status block
   was out of sync with the repo by one session. If this repeats,
   real work could get duplicated or shipped work could get reverted
   by accident. See §1.2 for the recommended mitigation
   (`scripts/current_status.sh`).
3. **Glossary is 90% stubs.** Deliberate per prompt §B.3. It is
   the structural keystone for NFR / IDs / RTM / OSS-Pro views,
   not a finished reference doc. Don't lean on it as authoritative
   for *definitions* until the `TODO — derive from …` stubs are
   populated.
4. **Four glossary-scoped open decisions** still in §11. AC house
   style and requirement ID scheme in particular block later gap
   work. If NFR lands next without locking a requirement ID scheme,
   it'll have to be retrofitted — plan accordingly.
5. **Non-functional requirements (audit gap #2) still scattered.**
   Latency / availability / resource budgets live in
   `plans/L*_system_design.md` + `planning/14_performance_tiers_vram.md`
   but aren't rolled up. `docs/NFR.md` is the natural next
   spec-package move after step 3 Memory plumbing ships.
6. **Two known flaky tests** remain unaddressed. Cross-cutting
   cleanup is explicitly out of scope for all current tracks.

---

## 5. Decisions log (new this session)

- **32. Prompt status blocks are not trusted over repo state.**
  When the two disagree, follow the repo and document the
  divergence in the commit body. Session prompts should be
  regenerated from the latest `HANDOFF_*.md`, not from memory.
- **33. Glossary is the first keystone; NFR is the second.**
  Forward-looking requirement IDs (audit gap #3) follow NFR, not
  the other way around, because the ID scheme benefits from being
  validated against a second concrete spec before being locked.
- **34. Rot guards and AC remain conceptually separate in all
  future glossary-referenced work.** Encoded in `docs/GLOSSARY.md`
  §6 and §0.

Carried (unchanged): 1–31 from prior handoffs.

---

## 6. Remaining backlog (priority-ordered)

1. **Memory V2 step 3** — per-domain write/read plumbing via the
   policy surface. **NEXT SESSION.**
2. `docs/NFR.md` skeleton — audit gap #2. Can be attempted in-
   session after Memory V2 step 3 lands if time remains.
3. Presence V1 step 4 — `tools/lint-presence-doc/` rot guard, flip
   doc to "current".
4. Memory V2 step 4 — Trust drawer Memory tab.
5. Real macOS / Linux idle probes for Presence.
6. Presence session-lifecycle axis (Foreground / Background /
   Closed).
7. Memory V2 step 5 — retention sweep.
8. Quality-Eval v1.2 — session-log replay importer.
9. Quality-Eval v1.3 — rot guard + `pnpm eval` wrapper.
10. Memory V2 step 6 — embeddings (opt-in, local-only).
11. Memory V2 step 7 — memory rot guard.
12. Forward-looking requirement IDs (audit gap #3).
13. OSS / Pro / Cross-system assembled views (audit gap #4).
14. Light RTM view from rot-guard manifests (audit gap #5).
15. `docs/AC-STYLE.md` (audit gap #6).
16. Cross-cutting — migrate `AETHER_PERSONAS_DIR` +
    `AETHER_OLLAMA_*` test seams to `TempDir` / scoped env.

---

## 7. Observations worth preserving

1. **L3 sub-layer watch.** The glossary §3 note: L3 currently
   hosts two orthogonal axes (assistant posture + user attention)
   as sibling types in one crate. If a third axis lands
   (session lifecycle is the obvious candidate), that's the
   trigger to revisit the L1–L7 partition. Until then, leave it.
2. **Prompt feedback loop is working.** The stale-prompt catch
   this session is evidence the anti-drift discipline (push back
   rather than accept-and-refine) is holding. Worth continuing.
3. **Glossary §9 intentionally under-populated.** Next
   spec-package pass (`docs/NFR.md`) will fill latency budget,
   availability, resource budget, router tier, performance tier
   in the same sitting. Don't backfill them individually.
4. **Coaching register watch.** Perplexity's output across the
   last 4 rounds has 0 disagreements on record. If a 5th round
   still produces only accept-and-refine, treat the whole
   exchange as a stylish mirror rather than an analysis. Keep
   pushing back.

---

## 8. Next recommended prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `a979ab7`, 18 commits ahead of `origin/dev`.
- Working tree clean. Push NOT pre-authorized.
- Vision V1, Voice V1: closed subsystems, rot-guarded.
- Presence V1 steps 1, 2, 3 complete. Step 4 (rot guard) pending.
- Memory V2 step 1, 2 complete. **Step 3 (L2 plumbing) is NEXT.**
- Quality-Eval v1.1 complete.
- Glossary skeleton shipped (`docs/GLOSSARY.md`) — structure only.

Mandatory first steps:
1. `git status` and `git log --oneline -30`. Verify the above.
2. Read `HANDOFF_2026-05-16_GLOSSARY.md` end to end.
3. Read `HANDOFF_2026-05-16_PRESENCE_MEMORY_EVAL.md` end to end.
4. Read `docs/MEMORY-V2-ARCHITECTURE.md` §§4, 5, 8.
5. Read `docs/GLOSSARY.md` §5 (capabilities) and §7.4 (memory).
6. Skim:
   - `packages/l2-memory/src/kernel.rs` — landing zone.
   - `apps/desktop/src-tauri/src/memory_config.rs` — policy surface
     step 3 consumes.
   - `packages/l5-policy/src/engine.rs` — decision flow gating the
     write path.

Session focus: **Memory V2 step 3 — per-domain write/read plumbing
via the policy surface.**

Scope:
- Thread `MemoryConfig::risk_for(domain)` into the memory write
  path so user-sensitive domains (Facts, Artifacts) flip from
  `NeedsUpgrade` to the proper `Ask` flow.
- Emit `MemoryWrite` / `MemoryForget` / `MemoryEdit` L5 capability
  events at the L2 kernel surface. Additive — legacy granular
  emissions remain.
- Emit `memory_written` / `memory_forgotten` / `memory_edited`
  telemetry kinds per design §5. Audit row per write. Sampled
  audit for reads (1 per ~100 per domain per session).
- Tests: per-domain routing, Ask-flow round trip for a Facts
  write, Auto-flow round trip for a Durable write.

Optional spec-package work (only if step 3 lands cleanly with time
to spare):
- Draft `docs/NFR.md` skeleton — audit gap #2. Consolidate
  latency/availability/resource-budget constraints scattered across
  `plans/L*_system_design.md` + `planning/14_performance_tiers_vram.md`.
  Structure + stubs only, keyed to `docs/GLOSSARY.md` §9.

Out of scope:
- Trust drawer Memory tab (Memory V2 step 4).
- Retention sweep (step 5).
- Embeddings (step 6).
- Rot guards (Memory V2 step 7, Presence V1 step 4).
- Forward-looking requirement IDs — defer until NFR lands, so the
  ID scheme is validated against a second concrete spec.

Hard constraints (still in force):
- No push. No release / signing.
- No `AuditRecordEvent` shape change.
- User-sensitive domains default Ask — do not flip.
- No new heavy dependencies.
- Do not destabilise vision / voice / presence rot guards.
- Dry-run evals must still be 6/6 pass.
- Do not touch the two known flaky tests
  (`yaml_persona_pack_merges_into_catalog`,
  `from_env_uses_defaults_when_vars_unset`).
- No retrofitting of requirement IDs or AC house style across
  history. Forward-only, and NFR first.
- Rot guards and AC remain conceptually separate (per
  `docs/GLOSSARY.md` §6).

Process:
1. Thread `MemoryConfig` into L2 write/read behind a small trait
   so the kernel doesn't depend directly on the shell's AppState.
2. Audit-row + telemetry emission on each write path.
3. Sampled read audit (1/100 per domain per session).
4. TS types + UI bindings for new telemetry kinds.
5. Tests.
6. Full check matrix (fmt, workspace, l4-router --test-threads=1,
   shell, lints, evals, pnpm typecheck/build/test).
7. Commit in scoped slices.
8. Execution report + fresh handoff.

Stay strictly on Memory V2 step 3. If you find yourself tempted
to do step 4 (Memory tab) or step 5 (sweep), stop and write the
next handoff instead.
```

---

(end of handoff)
