# Milestone 2 roadmap — 2026-04-24

> **AMENDMENT 2026-04-24 (same day, post-research):** Mini-Run 0 and run ordering
> revised after a web-research pass on the April 2026 local-LLM landscape plus
> a discovery that the original Run 1 (Retrieval Wiring) had no backing rows
> to retrieve over — the embed-eligible domains (Durable / Projects / Artifacts)
> have no durable store yet (carried forward from Milestone 1 as backlog 5.5a).
>
> **Mini-Run 0 (SHIPPED 2026-04-24, commit TBD this session):** ADR-0003
> supersedes ADR-0002 Decision 1. Text default pinned `gemma4` → `gemma4:e4b`
> (avoids silent `:latest` drift and the 31B Dense FlashAttention hang).
> Embedding default swapped `nomic-embed-text` → `bge-m3` (~25-point retrieval
> accuracy lift per April 2026 RAG benchmarks). Ollama stays as the runtime;
> no `mistral.rs` / `candle` / `ZML` pivot. Hygiene chore (`.gitattributes` +
> `current_status.sh` newest-handoff fix) shipped separately in commit 344fbcf.
>
> **Revised run order (supersedes the §Run 1 / §Run 2 sequencing below):**
>
> 1. **M2 Run 1 (was Run 2) — Durable Store + ADR-0004.** Ship first so
>    retrieval has real embed-eligible rows. Larger session.
> 2. **M2 Run 2 (was Run 1) — Retrieval Wiring.** Consumes real BGE-M3
>    vectors against the Durable store. Smaller session, cleaner demo.
> 3. Runs 3, 4, 5, 6 — unchanged in shape. ADR numbering shifts: CI ADR
>    becomes ADR-0005 (ADR-0003 was consumed by Mini-Run 0, ADR-0004 by the
>    new Run 1).
>
> The §below text is the as-written-this-morning plan. Treat the amendment
> as authoritative where they conflict; keep the original for milestone-close
> retrospective.

**Theme:** *Aether becomes retrieval-aware and user-facing.*

**Premise.** Milestone 1 made the five subsystems trustworthy. Memory V2 can write embeddings, but the turn engine doesn't read them yet — which means the most expensive piece of Milestone 1 (embeddings infrastructure) has zero user-visible effect. Milestone 2's job is to close that loop, make the opt-in frictionless, and do the documentation work that pays back once the feature is real.

**Ordering principle.** Close the loop first (Run 1 retrieval wiring), then remove the scale ceiling (Run 2 domain-typed durable store), then polish the path a new user walks (Run 3 onboarding), then pick up documentation + CI debt (Runs 4–5), finally add visible feedback (Run 6). Pragmatic variant below swaps 3+6 earlier if Don wants visible polish over infrastructure.

**Milestone close looks like:** Aether actually uses its memory on every turn. When embeddings are on, turns cite what was recalled; when off, behaviour is identical to Milestone 1. Documentation + CI have caught up to reality.

---

## Hygiene chore (ship inside Run 1, not as a run)

Two one-liners that don't deserve their own run but would stop recurring noise:

- **`.gitattributes`** — add `* text=auto eol=lf` to silence the per-commit LF/CRLF warnings. One line, retires a Milestone 1 retrospective finding.
- **`scripts/current_status.sh` + `.py`** — pick the newest `HANDOFF_*.md` by filename date instead of the hard-coded reference. Kills the stale-prompt class of bug (Milestone 1 retrospective §3 item 1).

Recommend bundling both into Run 1's first commit (`chore: silence CRLF warnings + current_status.sh reads newest handoff`).

---

## Run 1 — Retrieval Wiring

**Target.** Turn engine consumes `EmbeddingStore::query_nearest` for Durable / Projects / Artifacts recall when embeddings are enabled; soft-fallback to `SessionMemoryStore::recent` when not.

**Why first.** Biggest user-visible payoff of Milestone 1 Run 3. Everything else in Milestone 2 either depends on this or is more valuable once this exists.

**Precondition.** None beyond current state. Embeddings trait is live (`e135c2a`); `SessionMemoryStore::recent` already exists.

**Scope.**
- L5 capability question — propose: **MemoryRead already covers both paths** (same data, different source) and stays Low/Auto. OR introduce `MemoryRetrieve` if an auditor needs to distinguish embedding-augmented reads. **Reserved decision #M2-01** — don't silently ship.
- L4 router wiring: when `memory.json::embeddings.enabled == true`, recall path queries `EmbeddingStore::query_nearest` for the three embed-eligible domains; results union with `SessionMemoryStore::recent` under a deterministic ordering.
- **Determinism gate.** With embeddings **off**, turn output must be byte-identical to today. With embeddings **on**, ordering must be reproducible given the same corpus + same query vector.
- **Parallelism question.** Does retrieval block the turn, or run in parallel with prompt compilation? Propose: parallel with a short timeout (e.g. 250 ms) + silent fallback to session-only. **Reserved decision #M2-02**.

**Out of scope.** UI feedback (Run 6), provider swap, vector backend change.

**Done when.**
- `cargo test -p aether-l4-router --features …` includes on/off determinism tests.
- With embeddings off → no behavioural delta vs. `ad31f5d`.
- With embeddings on + 0 matching rows → same output as off (silent fallback).
- With embeddings on + matching rows → turn has access to them; shape decided by reserved decision.
- `docs/MEMORY-V2-ARCHITECTURE.md` §10 item 6+ reflects retrieval-is-live.

**Reserved decisions.**
- **#M2-01.** Capability name (reuse `MemoryRead` vs. new `MemoryRetrieve`).
- **#M2-02.** Retrieval timing (block vs. parallel-with-timeout) and timeout value.
- **#M2-03.** Union/rank strategy for embedding + session results.

**Commit cadence.** 2–3 commits: chore hygiene → router plumbing + capability wiring → tests + doc update.

---

## Run 2 — Domain-typed Durable Store

**Target.** Backlog item 5.5a. Populate Durable / Projects / Artifacts domains with a real store so retention sweep + embeddings both cover more than Session.

**Why second.** Retrieval (Run 1) has something to retrieve over — but the non-Session domains still have no backing store. Run 2 lifts the ceiling on Run 1's usefulness without blocking Run 1 from shipping.

**Precondition.** Run 1 merged (so retrieval is shaped by what domains actually hold rows).

**Scope.**
- **ADR-0003 required** — pick the store shape (reuse SQLite backend from Session, new per-domain tables, JSONL-flat, etc.). Do not silently decide.
- Extend retention sweep to walk real rows for Durable / Projects / Artifacts (not trace-skip).
- Extend embedding lifecycle: when a Durable / Projects / Artifacts row is forgotten, the paired embedding row is deleted in the same L5 audit write.

**Out of scope.** Facts / Preferences domains — deferred until a consumer appears.

**Done when.**
- ADR-0003 accepted + executed in the same run (pattern from Milestone 1).
- Retention sweep tests cover all four domains (Session + three new).
- Embedding + primary row lifecycles stay symmetric under forget.

**Reserved decisions.**
- **#M2-04.** Store shape (ADR-0003).
- **#M2-05.** Whether Facts / Preferences domains ship here or defer.

**Commit cadence.** 3–5 commits: ADR → store → sweep extension → embedding delete cascade → doc/tests.

---

## Run 3 — Embeddings Onboarding

**Target.** First-run experience: Ollama availability check, model-pull prompt, single toggle.

**Why third.** The opt-in flag is a "magic incantation" today (`memory.json::embeddings.enabled`). One click from Settings, with an Ollama-reachable check and a "pull `nomic-embed-text`" button, turns Milestone 1 Run 3's infra into something Don can demo without editing JSON.

**Precondition.** Run 1 merged (otherwise turning it on does nothing visible).

**Scope.**
- Settings drawer: availability check → if Ollama reachable, show toggle + model status; if not, show install link + block toggle.
- Backend: `ollama list` query, model-present check, model-pull trigger (long-running; progress bar optional).
- **No silent model pull** — explicit user action required.

**Out of scope.** Remote provider config, multi-provider UI.

**Done when.**
- Fresh profile with Ollama absent shows clear blocked state.
- Fresh profile with Ollama present shows model-pull CTA.
- Post-pull, toggle is functional and validates Milestone 1 Run 3 Risk B ("unverified on real workloads").

**Reserved decisions.** None — UI-only, no structural calls. If Don wants a specific visual language, request ahead of session start.

**Commit cadence.** 2 commits: backend checks → Settings UI wiring + tests.

---

## Run 4 — Spec Gaps #3–#6 Bundle

**Target.** Close all four outstanding spec package gaps in one documentation-shaped run.

- **Gap #3** — Forward-looking requirement IDs. **Still Don-reserved.** Do NOT pick up without explicit authorisation in the run's prompt. If not authorised, ship #4–#6 only and leave #3 for a later Don-signed run.
- **Gap #4** — OSS / Pro / Cross-system spec views.
- **Gap #5** — Light RTM (requirements traceability matrix).
- **Gap #6** — `docs/AC-STYLE.md` (acceptance-criteria style guide).

**Why fourth.** Documentation-shape work has no runtime dependency on Runs 1–3, so it can land any time — but it's most useful after Runs 1 + 2 expose real structure worth tracing. Bundling all four exploits shared research + editorial overhead.

**Precondition.** None runtime. Gap #3 requires Don's sign-off.

**Parallelism.** Can run in parallel with Run 5 if desired (different files, zero merge risk).

**Done when.** All four files exist, cross-linked from `docs/GLOSSARY.md`, and #4–#5 reference real artefacts from Runs 1–3.

**Reserved decisions.**
- **#M2-06.** Gap #3 authorisation (Don-only).

**Commit cadence.** 3–4 commits, one per gap.

---

## Run 5 — `pnpm eval` + CI Kickoff

**Target.** Repo's first real CI gate. Milestone 1 Run 5 Option B deferred this because the repo had no root `package.json` and no CI wiring; Milestone 2 adopts it as a first-class run.

**Why fifth.** After Runs 1–3, there are real behaviours worth regression-testing: retrieval determinism, onboarding flow, sweep coverage. CI becomes worth the setup cost.

**Precondition.** Runs 1–3 merged (so CI has the surface it claims to protect).

**Scope.**
- Root `package.json` (or `pnpm-workspace.yaml` if one already exists) exposing `pnpm eval`.
- `pnpm eval` runs `tools/evals/__main__.py --dry-run` + adversarial suite; non-zero exit on regression.
- GitHub Actions workflow: on PR to `dev`/`main`, run `cargo fmt --check`, `cargo check --workspace`, `cargo test --workspace`, `pnpm eval`, `pnpm test`, all rot-guard lints.
- **ADR-0004 likely** — CI scope (what blocks merge vs. what runs informational). Call it before ship.

**Out of scope.** Release automation, changelogs, secret rotation.

**Done when.** PR to `dev` runs the workflow, a green workflow is the default state, a broken test is caught by CI (verified by an intentional failing PR).

**Reserved decisions.**
- **#M2-07.** ADR-0004 scope (what CI blocks).
- **#M2-08.** Whether CI blocks merge today or runs informationally first (progressive tightening, like Wave 1 lint configs).

**Commit cadence.** 3–5 commits: ADR → package.json → workflow → test-the-test PR → doc.

---

## Run 6 — Memory Tab Polish

**Target.** Turn-level "recalled X" chips in the Memory tab / trust drawer, now that retrieval is live.

**Why last.** The highest-value UI polish, but it's literally impossible before Run 1 exists. Deferring it here keeps the run orderable without blocking.

**Precondition.** Run 1 merged. Run 5 not required.

**Scope.**
- Surface the list of recalled items for each turn in the Memory tab history view.
- "This turn recalled 3 items" summary; click-through reveals which.
- Opt-in/opt-out visibility respects embeddings flag.

**Out of scope.** Editing retrieval inline, re-ranking UI.

**Done when.** Memory tab shows per-turn recall context; frontend tests cover the new path.

**Reserved decisions.** None structural.

**Commit cadence.** 1–2 commits.

---

## Path map

| Run | Name | Target | Precondition | Parallel-safe with |
| --- | --- | --- | --- | --- |
| 1 | Retrieval Wiring | Turn engine reads embeddings | None | — |
| 2 | Durable Store | Backlog 5.5a + sweep | Run 1 | Run 4 |
| 3 | Embeddings Onboarding | Settings polish | Run 1 | Run 4 |
| 4 | Spec Gaps #3–#6 | Documentation bundle | None (runtime); Don for #3 | Run 2, 3, 5 |
| 5 | `pnpm eval` + CI | First real CI gate | Runs 1–3 merged | Run 4 |
| 6 | Memory Tab Polish | Recall chips | Run 1 | Run 4, 5 |

**Gate rules.**
- Run 2+3 both want Run 1 merged. Don't bundle them — they're different problem shapes.
- Run 5 is the first run that gets real value from Runs 1–3 together; don't ship it before them.
- Run 4's Gap #3 is Don-reserved regardless of order.

---

## Pragmatic variant (visible polish before infrastructure)

If Don wants user-facing momentum over infrastructure debt:

| Run | Milestone 2 base | Pragmatic variant |
| --- | --- | --- |
| 1 | Retrieval Wiring | Retrieval Wiring (unchanged — must be first) |
| 2 | Durable Store | **Embeddings Onboarding** (was Run 3) |
| 3 | Embeddings Onboarding | **Memory Tab Polish** (was Run 6) |
| 4 | Spec Gaps #3–#6 | **Durable Store** (was Run 2) |
| 5 | CI Kickoff | Spec Gaps #3–#6 (unchanged position) |
| 6 | Memory Tab Polish | CI Kickoff (unchanged position) |

Net effect: Runs 1→3 are all user-visible; infrastructure (Durable Store, CI) shifts later. Risk: Run 4 (Durable Store) lands after Run 2 (Onboarding) surfaces the non-Session emptiness to users, which means users may turn the feature on and see fewer recalled items than expected. Mitigation: scope Onboarding copy honestly ("Session memory only until durable store ships").

**Recommendation.** Base ordering. Runs 1 + 2 together unlock the feature properly before polish lands. Only swap if Don wants a demo-able moment fast.

---

## Hard constraints (inherited)

- Doctrine rules unchanged. L5 is the single writer for side effects. No raw-media persistence. Additive by default. Private assets stay out of public distributables. No silent fallback.
- 70 numbered decisions (#1–#70) carry forward. Milestone 2 decisions start at #M2-01 to keep them clearly labelled as second-milestone (merge-in style at milestone close).
- Reserved decisions stay reserved. Any run that wants to resolve one either gets Don's sign-off in the prompt or defers.
- ADRs precede cross-layer refactors (Milestone 1 retrospective §4 invariant). ADR-0003 (Run 2) and ADR-0004 (Run 5) both expected.

---

## What success looks like at milestone close

- Aether actually uses its memory on every turn. Turning embeddings on is one click. Turning them off restores today's behaviour bit-for-bit.
- Retention sweep covers four domains, not one. Durable / Projects / Artifacts rows live somewhere inspectable.
- CI catches a broken PR. A green `pnpm eval` is the default state of `dev`.
- Spec gaps #4–#6 (minimum) are closed; #3 closed if authorised.
- At least one ADR (0003) accepted and executed; 0004 likely.
- Memory tab shows per-turn recall, proving the loop closed.

---

(end of roadmap)
