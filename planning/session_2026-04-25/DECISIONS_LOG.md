# Session 2026-04-25 — Autonomous decisions log

> Each entry below is a blocker-level decision made without Don's
> direct ratification, in keeping with the "all-level decision
> authority" delegation in `HANDOFF_2026-04-25_NEXT_AUTONOMOUS_SESSION.md`.

## D-001 — Audit row schema v1 had no `utterance` field at all

**Context.** ADR-0009 §Decisions 1-2 + the handoff §4A scope speak of
"the audit row currently stores the augmented utterance". On reading
`packages/l5-policy/src/audit.rs::AuditRecordEvent`, this is wrong:
the v1 audit row has **no utterance field whatsoever**. The
augmentation pollution lives entirely in `TurnRequest.utterance`,
which the L1 engine forwards to the router. The audit row records
capability/resource/decision, not user text.

**Decision.** Implement ADR-0009 with the corrected reading: schema
v1 = no utterance, v2 = adds `original_utterance: Option<String>`
plus `retrieval_provenance: Option<RetrievalProvenance>` and an
explicit `schema_version: u32`. Existing rows deserialize as v1
implicitly via `#[serde(default = "schema_version_v1")]`.

**Why this is fine for the ADR's intent.** The user-visible bug the
ADR fixes is "audit-by-phrasing search doesn't work". v1's fix-state
was "no phrasing in audit at all" — strictly less leaky than the
ADR's framing. Path A (split TurnRequest fields) is still the right
shape: it gives every future audit consumer a stable
`original_utterance` and decouples the prompt-builder from the
audit truth.

**Open Items resolution (per handoff scope #7).** All three Open
Items in ADR-0009 §"Open items":
- Provenance lives **on the audit row**, not a sidecar table. A
  sidecar would require a join on every audit read; the audit row
  is already small and the new field is `Option<_>` so non-text
  capabilities pay no cost.
- Absent `schema_version` field means **implicit v1**. Cheaper, and
  the version is recoverable any time a row gets re-serialized
  through a v2-aware writer.
- The "model-saw" UI toggle is **deferred** to a future ADR. The
  AuditList expandable in this ADR shows the retrieval hit count
  and domains; surfacing the full `model_input_utterance` requires
  carrying it on the audit row, which (a) would re-introduce the
  pollution we just removed and (b) blocks on a separate
  reproducibility-replay design that is out of scope here.

## D-002 — Plumbing path: `ActionRequest::audit_extras: Option<AuditExtras>`

**Context.** The L5 PolicyEngine writes audit rows internally inside
`engine.rs::write_audit`. The shell does not directly construct
`AuditRecordEvent`. Threading `original_utterance` and
`retrieval_provenance` from the shell through `submit_turn` →
`TurnRequest` → L1 engine → `ActionRequest` → L5 evaluator → audit
write requires one new optional field on `ActionRequest`.

**Decision.** Add `pub audit_extras: Option<AuditExtras>` to
`ActionRequest`. `AuditExtras` is a small struct re-exported from
`audit.rs` carrying the optional original utterance + retrieval
provenance. `write_audit` reads it when present and stamps the audit
row with v2 fields; absent → v1-shaped row.

**Why.** The alternative (a new
`evaluate_with_audit_extras(...)` method) doubles the trait
surface for one capability path. Optional field is wire-additive
(serde default), and the trait stays single-method.

## D-003 — `TurnRequest` keeps `original_utterance` + `model_input_utterance`; legacy `utterance` field removed

**Context.** ADR Path A spec: "Add `original_utterance: String` and
`model_input_utterance: String`". Handoff scope §1: "Prefer removing
the existing `utterance` field cleanly over keeping it."

**Decision.** Remove the `utterance` field from `TurnRequest` in
the same commit. Eight call sites under `apps/desktop/src-tauri`,
`apps/l1-cli`, and the L1 test crate; all updated. No backwards
shim. Wire-breaking but the type is internal to the workspace
(no external consumers per `packages/l1-interaction/README.md`).

**Why no shim.** A serde-default `utterance` shim would let stale
callers compile but silently set `model_input_utterance == ""`,
producing rows that look like the user said nothing. Hard
compile-error is the cheaper failure mode.

## D-004 — `lint-policy-doc/check.py` does not exist; created in this session

**Context.** Handoff scope §6 says "Update expected anchor count" in
`tools/lint-policy-doc/check.py`. The file does not exist on tip
4614ae7.

**Decision.** Create `tools/lint-policy-doc/check.py` modeled on
`tools/lint-memory-doc/check.py`. The doc it guards is
`docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md`
(it's the only policy/audit doc with anchorable claims this session
touches). Anchors cover the new fields, struct, and the L1/L5
plumbing.

**Why.** A fresh rot-guard for ADR-0009 is consistent with the
established pattern (lint-memory-doc, lint-presence-doc,
lint-quality-doc, lint-vision-doc, lint-voice-doc). Adding it now
prevents the new symbols from drifting under future renames.

## D-005 — Doc-anchor drift: update prompt citations rather than add anchors

**Context.** `planning/OPEN_QUESTIONS.md` line 167 carried an [OPEN]
flag: prompt `planning/prompts/L5_policy_engine_system_design.md`
cited `12_permissions_autonomy.md §9.4` and
`13_trust_security_redteam.md §10.3`, neither of which exist.
Both `planning/plans/L5_policy_engine_system_design.md` and
`planning/plans/implementation_prep/L5_interface_pack.md` already
work around this by treating the actual existing sections as
canonical and flagging the drift in their respective §14.

**Decision.** Update the prompt to reference the actually-existing
sections: `12_permissions_autonomy.md` "Capability groups" + "Non-
negotiable blocks (hardcoded platform rules)" and
`13_trust_security_redteam.md` "Red-team focus areas" §3–§6.
OPEN_QUESTIONS line 167 flipped to [DECIDED 2026-04-25] with this
log as provenance.

**Why update prompts not source files.** Adding back-fill anchors
(`§9.4`, `§10.3`) to `12` and `13` would force a renumber of every
section after the insertion point, cascading to every other prompt
and plan that cites the canonical files. Updating the citation is
local and surgical; the system-design plan already proves these
new anchor paths work.

## D-006 — Phase 3C: ceiling is model-count, not VRAM (Forge tier)

**Context.** Phase 3C handoff scope expected the `gemma4:26b` add to
either coexist with the baseline trio or evict on VRAM pressure.
Neither happened cleanly — the binding ceiling we hit was Ollama's
`OLLAMA_MAX_LOADED_MODELS=3` default, and `gemma4:26b` additionally
forced solo residency at 94% card use.

**Decision.** Document the empirical ceiling in
`planning/session_2026-04-25/MULTI_MODEL_CEILING_REPORT.md` and
propose (not commit) an ADR-0006 §6 framing update: treat
`OLLAMA_MAX_LOADED_MODELS` as a first-class tier-tunable for Forge,
since the 24 GB card has ~7 GB of stranded headroom under stock
config. Numerical reservations in §6 (~4 GB Flame, ~8 GB Forge)
remain intact; only the operational framing shifts.

**Why no in-flight ADR edit.** Per Phase 3C constraints, ADR-0006
edits are a separate ratification commit. The proposed delta is
surfaced in the report for Don to ratify.

**Substitutions vs. handoff plan.** None. `gemma4:26b` was available
locally (17.99 GB on disk) so the substitute-large-model fallback
(`gpt-oss:20b`, `qwen2.5:32b`) was not needed. The probe order was
re-arranged from the handoff: a 4th *small* model (`qwen3:1.7b`,
1.36 GB) was attempted **before** `gemma4:26b` to isolate whether
the constraint is VRAM or model-count. That re-ordering is what
exposed the count cap as the binding constraint.

**Headroom finding.** Baseline trio resident = 16736 MB nvidia-smi
(12.9 GB ps-sum). 4th-model load evicted `gemma4:e4b` despite
~7.8 GB free VRAM at the eviction moment — proving the constraint
was count, not bytes. `gemma4:26b` solo residency = 23051 MB
(94% of card), 1513 MB headroom remaining.

**Concurrent-agent note.** This decision was logged as D-006 because
another agent in this session already used D-005. The two
decisions are independent; the numbering simply reflects log
arrival order.

## D-007 — `EmbeddingStore::embedded_ids` returns `HashSet<MemoryId>` with default impl returning empty

**Context.** Phase 2 (handoff §4B) adds an enumeration method to the
`EmbeddingStore` trait so backfill can skip already-embedded rows on
the second pass. Three sub-decisions:

1. **Return shape.** Handoff suggested `HashSet<String>`. `MemoryId`
   is the existing typed key on every other trait method (`upsert`,
   `delete`, `EmbeddingRow::memory_id`). Returning `String` would
   force the consumer to wrap on every `contains` probe.
2. **Default impl vs required.** A default returning empty set
   means a stale `impl EmbeddingStore` keeps compiling but reverts
   to historical brute-force re-embed.
3. **Skip-count surfacing.** New `BackfillProgress` field
   `skipped_already_embedded` rather than folding into `completed`.

**Decision.**
1. `HashSet<MemoryId>` — typed handle, O(1) probe, no allocation
   churn in the hot loop.
2. **Default impl returning `Ok(HashSet::new())`.** The semantic
   contract of an empty set is "skip nothing", which is strictly
   safer than an over-eager "everything-already-embedded" default
   that would silently drop work. `FlatFileEmbeddingStore` overrides;
   any future store author has a compile-time green path with
   correctness preserved by `upsert` idempotency.
3. **Surfaced separately.** `BackfillProgress` gains
   `skipped_already_embedded: usize`. The UI's
   `BackfillProgressView` computes `processed = completed +
   skipped_already_embedded` for the bar percentage so skip work
   advances the progress strip; the post-run summary line and the
   in-progress text both call out the skip count distinctly. Folding
   skipped into completed would lie about how much real embed work
   landed and obscure the cheap-path win.

**Why no Tauri command for `embedded_ids` directly.** The new method
is consumed in-process by the backfill worker — exposing it as an
IPC surface would invite UI calls that duplicate state better held
in `BackfillProgress`. Keep the trait surface internal.

**Doc + lint.** `docs/MEMORY-V2-ARCHITECTURE.md` §"Embedding
backfill" updated to reflect the implemented fast path (was: "Open"
flagged as future work). Three new rot-guard anchors added to
`tools/lint-memory-doc/check.py`: `fn embedded_ids` in
`packages/l2-memory/src/embeddings.rs`, the
`skipped_already_embedded` field in `state.rs`, and the
`embedded_ids(domain)` call site in `backfill.rs`. Anchor count
112 → 115.

**Test deltas.** l2-memory lib 33 → 37 (+4: empty store, domain
isolation, upsert-replace+delete, persistence roundtrip). desktop
src-tauri 275 → 278 (+3: second-pass full-skip, mixed
completed/skipped, cancel during skip walk). Frontend vitest
217 → 218 (+1: post-run summary surfaces skip count).

## D-006a — ADR-0006 §6 ratification: `OLLAMA_MAX_LOADED_MODELS` surfaced as Forge tier-tunable

> **Numbering note (added 2026-04-25 cleanup):** This entry was originally
> filed as **D-007** by the ADR-0006 §6 update agent at the same moment Phase 2
> filed its own D-007 (HashSet enumeration shape). To preserve forward-monotonic
> numbering and unique IDs without disrupting downstream D-008+ references,
> the ADR-0006 §6 entry was renumbered to **D-006a** as a sub-decision
> following the D-006 multi-model ceiling finding it directly ratifies.
> The Phase 2 D-007 entry remains canonical.

**Context + decision.** Following Phase 3C's empirical finding (D-006: stock Ollama caps coexistence at 3 models, stranding ~7 GB on the 24 GB Forge card), the proposed §6 delta from `MULTI_MODEL_CEILING_REPORT.md` was ratified into ADR-0006 as a §6 amendment (status remains Accepted). The amendment adds an "Operational tunable" subsection naming `OLLAMA_MAX_LOADED_MODELS` as a first-class tier-tunable, recommending `=4` on Forge (baseline trio + future avatar slot per ADR-0008) while leaving Spark/Flame on the stock default of 3 (VRAM binds first on those tiers). Numerical reservations (~4 GB Flame, ~8 GB Forge) were left intact; only the operational framing shifted. §1–5 and §7+ untouched. Atomic commit, pushed to `dev`.

## D-008 — Phase 4D: `start_backfill` async via `Arc<AppState>` + `spawn_blocking`

**Context + decision.** The synchronous `start_backfill` Tauri command (live since v1) blocked the IPC thread for the entire backfill duration — empirically 30-60 sec on personal-scale histories at bge-m3 throughput, and unbounded once embedding row counts grow. AUTONOMOUS_RUN_FINAL_REPORT §9 shortcut #1 had this flagged. Phase 4D resolved it by (1) wrapping the Tauri-managed `AppState` in `Arc` so the worker task can hold a clone independent of the IPC thread's `State<...>` borrow lifetime, and (2) routing the live command through the previously-dead-code `spawn_backfill`, which dispatches the worker on `tauri::async_runtime::spawn_blocking`. The IPC call now returns within milliseconds with the just-initialised progress snapshot; live progress already flowed through the existing `backfill:progress` event stream so no frontend rewiring was required, only an adjustment so `handleBackfill` stops treating the now-initial return value as the final progress. Worker stays sync because per-row `provider.embed` is blocking HTTP plus `std::thread::sleep` pacing; placing it on async `spawn` would starve the runtime, so `spawn_blocking` is the correct primitive.

**Arc<AppState> migration cost.** Surgical, not invasive: every `State<'_, AppState>` parameter in `commands.rs` and every `app.try_state::<AppState>()` call in `main.rs` was rewritten mechanically to `Arc<AppState>`. Field access and method calls auto-deref through the second `Arc` layer, so 40+ call sites needed no body changes. Only two helper-function call sites that pass `&AppState` directly (`run_retrieval_context`, `backfill::estimate_unembedded_count`) were switched to `state.inner().as_ref()`. No engine crate touched, no public API broken. cargo test --all-features 278 → 281 (+3 Phase 4D tests), workspace tests unchanged, vitest 218 unchanged.

**Event emission shipped or deferred.** Shipped — but it already shipped in Phase 2; the worker's `emit_progress` and `emit_done` calls were live the whole time. Phase 4D only made them generic over `R: Runtime` so MockRuntime can drive end-to-end tests against a real spawned task. Frontend `RetrievalTab.tsx` continues to consume both polling (`backfill_status` every 5 sec via `POLL_INTERVAL_MS`) and live events (`onBackfillProgress` + `onBackfillDone`). Per Handoff §7 lesson #3 the polling is acceptable; the events are belt-and-braces.

**Double-start handling.** Hardened with `compare_exchange` on `backfill_in_progress` inside `spawn_backfill`. Two simultaneous `start_backfill` IPC calls can no longer both pass the guard — the loser gets `None` and `start_backfill` surfaces it as `Err("backfill already in progress")`. New test `double_spawn_backfill_returns_none_on_second_call` exercises this against a real spawned worker. Cancel cadence verified by `cancel_during_spawned_run_exits_within_200ms_with_cancelled_flag`: 200 ms budget honoured (with 5 ms per-row pause).

**D-number clash note.** The parallel ADR-0006 §6 ratification agent filed its decision as D-007 alongside the Phase 2 D-007 entry already at the bottom of this log. Phase 4D therefore takes D-008 to keep numbering forward-monotonic; the duplicate D-007 should be reconciled by the next agent that touches this file (renumber the ADR-0006 entry to its own slot or move it to D-006.5 — Don's call).

## D-009 — Phase 7 Quality-Eval V2: persona prompt sourced from `persona.yaml` directly, not from L6 compiler

**Context.** Phase 7 needed a "persona compile path" the eval harness
could call to produce the system prompt the model would receive. The
Rust `packages/l6-persona/src/default_compiler.rs` exists and produces
a templated voice/stance prompt from typed `PersonaProfile` dials.

**Decision.** Skip the L6 compiler. The harness reads
`personas/<id>/persona.yaml` and pulls the canonical hand-authored
`personality.system_prompt` directly. For Aurora (the only persona
shipped on tip a9a55cf) this is the prompt locked by
`docs/PERSONA-SCHEMA.md` §6 step 8 ("never LLM-regenerated").

**Why.** The L6 templated prompt is a strict downgrade from the
hand-authored prompt for evaluation purposes — the shipping product
uses the hand-authored prompt, so the harness should too. Mirroring
L6 in Python would also drag the harness across the workspace
boundary into Rust-typed territory (`PersonaProfile`, `Stance`,
`Tone`, `Verbosity`, `Humor`) without buying any evaluation fidelity.

**Trade-off.** Personas without a `personality.system_prompt` field
in their pack cannot be composed for evals until either (a) they grow
one, or (b) a future slice ports the L6 templater into the harness.
Acceptable: the v1 product convention is to hand-author the prompt.

## D-010 — Voice composition stubs the STT path; no real audio routed to gemma4:e4b

**Context.** `gemma4:e4b` advertises an "audio" capability in its
Modelfile. Phase 7 voice composition could theoretically pipe real
.wav fixtures through `/api/chat`'s audio field. The voice scenario
expects the model to preserve the proper noun "Karpathy".

**Decision.** Stub the STT path with a name-keyed transcript manifest
in `tools/evals/composition.py::_VOICE_TRANSCRIPTS`. The transcript
is spliced into the user turn as `[transcript: ...]`. No audio bytes
reach the model.

**Why.** Three reasons:
1. The Ollama `/api/chat` audio field is not yet uniform across
   Ollama versions (0.21.2 on this hardware advertises gemma4 audio
   capability but the wire format is in flux).
2. The eval signal is **language behavior downstream of STT**, not
   STT quality itself. Routing real audio adds STT fidelity as a
   confound to language-behavior failures.
3. The transcript manifest makes adding new voice scenarios cheap:
   one map entry per fixture, no audio editing.

**What this masks.** A real STT failure that drops the proper noun
would be invisible to this slice. When Aether ships its own STT
adapter, a Quality-Eval V3 scenario kind that asserts on the
adapter's transcript output (rather than on downstream language
output) would close that gap.

## D-011 — Phase 7 commit message mismatch on tree commit `5e5530f`

**Context.** During Phase 7 commit 1, `git add tools/evals/composition.py
tools/evals/test_composition.py` succeeded but `git commit` landed
`planning/session_2026-04-25/SECURITY_REVIEW.md` instead — a
concurrent autonomous-session agent's untracked file ended up in
the index between the add and the commit, swapping my staged
changes for theirs while keeping my commit message.

**Resulting state.** Commit `5e5530f` is titled
`feat(evals): composition.py — persona/memory/vision/voice composers
for scenario runs` but actually adds 130 lines of SECURITY_REVIEW.md.
Commit `5d32487` lands the actual composition.py + tests under a
corrected message.

**Decision.** Do not amend or revert `5e5530f` from this autonomous
session — destructive history rewrite without Don's ratification
violates the global git-safety protocol. The mismatch is documented
here and in the `5d32487` commit body so a future audit can find it.

**Suggested follow-up for Don.** Either:
- Leave the historical record as-is (the diff is correct, only the
  subject is wrong; the SECURITY_REVIEW.md is itself a real
  artifact authored by the parallel agent).
- Use `git rebase -i` interactively to reword `5e5530f` to its
  actual content (e.g. `docs(security): session 2026-04-25 review`).

**Lesson.** Concurrent autonomous-agent sessions need an index-lock
discipline. Two cheap mitigations: (a) `git diff --cached` before
every commit; (b) a tiny pre-commit hook that fails when the
staged set does not match a sentinel manifest the agent wrote
out before staging.

## D-012 — Security fix pass: HIGH-1 fixed, MEDIUM-1 deferred, MEDIUM-2 fixed (Phase ad-hoc)

**Context.** The session-end security review (`SECURITY_REVIEW.md`)
flagged one HIGH (audit hash-chain breaks across v1→v2 schema
boundary) and two MEDIUMs. This pass triages and lands fixes within
the L5 layer scope only.

**Decision — HIGH-1 (FIXED, commit `88eefe5`).**
`packages/l5-policy/src/audit_seal.rs::canonical_bytes` now
dispatches on `row.schema_version`. v1 rows hash through a frozen
narrow `CanonicalAuditPayloadV1` struct that reproduces the
pre-`f378ea5` byte layout exactly; v2 rows hash through the wide
`CanonicalAuditPayloadV2` (which carries `schema_version`,
`original_utterance`, `retrieval_provenance`). v3+ falls through to
the wide branch for forward-compat. Picked the two-frozen-structs
shape over `serde-skip-if` because explicit field lists make the v1
contract auditable at a glance — a future field added to
`AuditRecordEvent` cannot accidentally break legacy chains.

Regression test `cross_schema_chain_replay_verifies_v1_then_v2` in
`packages/l5-policy/tests/audit_seal.rs` seals a v1 row, then a v2
row on top, and verifies the chain end-to-end. Plus three pinning
tests for the canonical-byte shape per version.

**Decision — MEDIUM-1 (DEFERRED).**
The `format!("{:?}", h.domain).to_lowercase()` Debug-formatter
construction lives in `apps/desktop/src-tauri/src/commands.rs` line
301 (`retrieval_provenance_for`), not `retrieval.rs`. Phase 4D
holds a write-lock on `commands.rs` for this session
(per-task brief). Touching that file would race Phase 4D's
`start_backfill` async refactor. Deferred to a follow-up session
that owns `commands.rs`. The fix is well-scoped: replace
`format!("{:?}", h.domain).to_lowercase()` with `h.domain.label()`
(method already exists, used elsewhere in the same file at line
2473) and add a unit test pinning the four lowercase variant
strings.

**Decision — MEDIUM-2 (FIXED, commit `ce9f007`).**
Cap value chosen: **16**, per the security review's recommendation.
Fix lives in two places defensively:
1. `RetrievalProvenance::new(block_present, hits)` constructor
   truncates writer-side.
2. `engine.rs::write_audit` defensively re-truncates in
   `audit_extras` before sealing — the last point of control before
   the canonical hash and DB row insert.

`RETRIEVAL_PROVENANCE_HITS_CAP` is exported from the crate root so
the desktop shell's eventual `retrieval_provenance_for` rewrite
(MEDIUM-1) can reference the same constant.

**Process incident.** First MEDIUM-2 commit attempt (`ede9cf4`)
captured Phase 7's untracked planning files (`QUALITY_EVAL_V2_*`)
into the L5 commit because `git commit` without explicit pathspec
walks the staging area at execution time, and Phase 7 added files
between my `git status` check and the commit. Reverted via
`75a3eec`; redone with `git commit -o <files>` to scope strictly to
the three L5 source files. Phase 7 will need to recommit its
planning files. This restates D-011's lesson — concurrent agent
sessions need an index-lock discipline.

**Test counts.** `cargo test -p aether-l5-policy --all-features`:
57 → 65 (+4 audit_seal tests, +4 audit.rs tests). `cargo test
--workspace` clean. `python tools/lint-policy-doc/check.py` OK.

## D-013 — Phase 3B: Option B (Python pacing-mirror bench), not Option A (Tauri integration test)

**Context.** Phase 3B (sustained backfill stress, HANDOFF §3B) offered
two procedures: (A) full Tauri integration test under
`apps/desktop/src-tauri/tests/`, or (B) standalone Python script that
hammers the Ollama embed endpoint at exactly the pacing the production
worker uses (`backfill::DEFAULT_PER_ROW_PAUSE_MS = 50`). The phase
prompt allowed Option B "if integration test plumbing is too heavy" —
which it was: Phase 4C is concurrently editing `state.rs` and Phase 4D
just landed `Arc<AppState>` plumbing in `main.rs`, so adding a 300+ LOC
test harness that constructs `AppState`, mocks the L5 policy gate, seeds
`durable_memory`, and races against parallel agent edits would risk
merge conflicts and offer marginal additional fidelity over Option B
(the backfill loop IS sequential `provider.embed + sleep`).

**Decision.** Option B. Script lives at
`planning/session_2026-04-25/bench_backfill_stress.py`; raw timeline at
`planning/session_2026-04-25/backfill_stress_results.json`; narrative
report at `planning/session_2026-04-25/BACKFILL_STRESS_REPORT.md`. No
production code touched.

**D-number note.** Both this entry and the security agent's claim D-012;
this entry takes D-013 to keep numbering forward-monotonic. The two
agents arrived at the log nearly simultaneously.

**Headline result.** 1000 rows × bge-m3 × 50 ms initial pacing
(auto-bumped to 100 ms after the first 500 at row 20):
- 4.71 min wall-clock — within ADR-0007 D7's "~3-5 min" projected band, top half.
- 3.54 rows/sec sustained (vs D7's 5 rows/sec extrapolation — 30% slower).
- 181.8 ms ± 19.5 ms per-row mean.
- 1.3% failure rate (13/1000 HTTP 500s) at almost-perfect 50-row cadence — pacing mitigates but does not eliminate Ollama's internal pressure mode.
- Steady-state VRAM 5519 MiB, 0 MiB creep over 280 s.
- Throughput drift -15.6% (got faster after ~400-row warmup).

**Real bug found, NOT fixed in this session.** The 1.3% failure rate
suggests an Ollama internal cadence (every ~50 rows) that pacing alone
cannot suppress. The backfill worker correctly counts these as failures
and continues (matches design); residue is recovered by Phase 2's
`embedded_ids` skip-path on the next invocation. Per phase prompt
constraint ("if integration test reveals a real bug, document it,
don't try to fix in this commit — would risk conflict with Phase 4D's
just-landed work"), the F1-F3 follow-ups in the report are documented
but not implemented:
- F1: per-row retry-on-500 with backoff in `run_backfill_worker`
- F2: distinct failure-count surface in `BackfillProgressView`
- F3: upstream investigation of the 50-row Ollama cadence

**Proposed ADR-0007 D7 §Tuning notes update.** Drafted in
BACKFILL_STRESS_REPORT.md §6, **not committed**. Replaces the
50-row-extrapolated 1000-row estimate with the sustained-real numbers
above. Recommendation: keep the 50 ms pacing default (100 ms costs
15-20% throughput for an incomplete reduction in the 500 rate; the
1.3% un-embedded residue is the cheaper failure mode given the skip-path
recovery).

**Why no ADR edit this session.** Per quality standard #8, ADR
modifications happen when implementing the ADR's decisions, not as
side-effect of validation. The proposed delta is propose-only — Don
ratifies (or a future session that lands F1's retry-on-500 ratifies as
part of that change).

## D-014 — Phase 4C: HuggingFace embedder via persistent Python helper subprocess (Path X)

**Context.** ADR-0007 D7 named `bge-small-en-v1.5` as the Spark-tier
embedding default; DECISIONS_LOG D-001 substituted `nomic-embed-text`
via Ollama because no HF loader existed. Phase 4C closes that gap.
The handoff scope (HANDOFF §4C) named three architectural paths:
**Path X** = subprocess to a Python helper using
`sentence-transformers`; **Path Y** = native Rust via
`candle-transformers`; **Path Z** = HF Inference API (out of scope —
local-only).

**Decision.** Path X.

**Why Path X over Path Y.** Path Y (candle) is in-process and zero-
Python but pulls a ~50-crate dependency tree (candle-core, candle-nn,
candle-transformers, plus tokenizer crates) and requires per-model-
family BERT pipeline code. The build-time cost (~5 min cold cargo
build) and the per-model code lift are both larger than the
subprocess overhead this provider eats. Path X matches existing repo
infrastructure (`tools/evals/`, `planning/session_2026-04-25/bench_*.py`
all use Python helpers for AI workloads), reuses the user's existing
`sentence-transformers` install if present, and lets `bge-small-en-v1.5`
work today.

**Cost shape Path X eats.**
- First helper spawn: ~2 s Python import.
- First model load (cold cache): ~10 s download + ~5 s warm.
- Subsequent embeds against same loaded model: <100 ms.
- Per-embed protocol overhead: ~5 ms stdin write + stdout read.

These numbers make the helper viable for the 1000-row backfill
workload (estimated 1-2 min wall-clock) and the everyday per-turn
retrieval embed (single-text, well under the user-perceptible
threshold).

**Wire protocol.** Newline-delimited JSON over stdin/stdout. One
request per line, one response per line. Request shape:
`{"op":"embed","model":"<id>","text":"<text>"}`. Response shape:
`{"ok":true,"vector":[...],"dim":<n>}` or
`{"ok":false,"error":"<msg>","kind":"load|embed|protocol"}`. The
`kind` field lets the Rust caller distinguish recoverable load
failures from protocol catastrophes.

**Model-cache strategy.** The helper holds a `dict[model_id ->
SentenceTransformer]` in process memory. Lazy-loaded on first request
per model. A long-lived helper that sees 5 different models will hold
all 5 in RAM (~130 MB each for bge-small-class). For Aether's
single-active-provider design this is at most one model at a time.

**Env-gating for tests.** The unit test
`embed_against_live_helper_returns_expected_dim` requires
`AETHER_HF_TEST=1` to run — without the gate, every cargo test run
would download 130 MB and pay 15 s on first invocation. The gate
keeps the dim-check available as a smoke test without poisoning CI.

**Smoke-test result.** `embed_against_live_helper_returns_expected_dim`
runs green with `AETHER_HF_TEST=1` set; bge-small-en-v1.5 returns
384-dim vectors as expected. (Logged as part of the Phase 4C
verification — vector dim was the only assertion needed; semantic
quality is established by ADR-0007 / DECISIONS_LOG D-001 for this
model class.)

**Deferred follow-up.** Native-Rust path (Path Y) tracked here as
next-window work. Triggers: (a) build-system PR that drops Python
runtime entirely, or (b) sentence-transformers becomes maintenance-
unfriendly (pip-install pain on Don's hardware tier in the wild).
Neither is current.

**Forward note for handoff.** The provider is wired but Don has not
flipped his `memory.json::embeddings.provider` to the hf: form. The
default Spark substitution (D-001 → nomic-embed-text via Ollama)
remains in effect for fresh installs; switching is opt-in.

## D-015 — Phase 3A: rank-function recall@1 fell 25.6 pp at 842-passage scale; ADR-0010 drafted (Proposed)

**Context.** Phase 3A per HANDOFF §3A required real-corpus calibration
of the production rank function in `apps/desktop/src-tauri/src/retrieval.rs::run_retrieval_context`
(cosine desc, recency tiebreak, truncate). 150-passage Block 5
baseline was 95% recall@1 / 0.975 MRR on bge-m3. (Numbered D-015
because two earlier writers both used D-007 in this log; the next
free integer keeps log arrival deterministic.)

**Corpus generated.** 60 synthetic conversation threads via
gemma4:e4b, 848 turns total, 72 cross-thread reference pairs as
ground truth. 6 rows NaN-skipped at embed time (U+FFFD characters
from the generator's en-dash output round-tripping through Windows
cp1252). Final embedded corpus: 842 turns × 1024d on bge-m3.

**Result.** recall@1 = 0.694, recall@3 = 0.833, recall@5 = 0.875,
recall@10 = 0.903, recall@20 = 0.958, MRR = 0.776. Both decision
triggers (recall@1 < 90%, MRR drop > 5%) fired.

**Decision.** Drafted `docs/adr/ADR-0010-rank-function-recency-weighted-combine.md`
as **Proposed** (NOT Accepted, per Phase 3A constraint). The ADR
sketches three options:
- Option A — recency-weighted combine (handoff's suggested fix)
- Option B — cross-encoder re-rank pass (bge-reranker-v2-m3)
- Option C — defer + document the recall@1 = 0.694 floor

**Why three not one.** Miss-pattern analysis (in
`planning/session_2026-04-25/RETRIEVAL_CALIBRATION_REPORT.md` §4)
shows the dominant failure mode is within-thread top-1 confusion
(the rank function correctly identifies the right thread but picks
topic-establishing intro turns over the specifically referenced
turn). This is NOT a recency-bias failure. Option A is unlikely to
be the right fix on its own. Option B (re-ranker) is the natural
remedy for within-thread specificity but is heavier to land.
Honest report rather than a reflexive recency-weighted commit.

**Did NOT modify `retrieval.rs`.** Calibration-only per Phase 3A
constraints. Don ratifies ADR-0010 (or directs an alternative path)
on return.

**Did NOT modify ADR-0007 D7 §Tuning notes.** The handoff's
"otherwise: report-only with one-line addendum" branch did not fire;
the ADR-trigger branch fired instead. Tuning addendum becomes
relevant only after the chosen ADR-0010 option is measured.

**Sanitization side-finding.** The 6 NaN-skipped rows were caused by
U+FFFD replacement characters in the embed input. The same pattern
will surface in production if the real Aether corpus ever carries
mojibake. Recommended follow-up (out of scope here): add
`text.replace('�', ' ')` to the production embedding path
in `packages/l2-memory/src/embeddings.rs` before the next backfill
iteration.

## D-016 — Sanitize U+FFFD at the embedding-provider boundary (closes D-015 follow-up)

**Context.** D-015 surfaced six bge-m3 embed failures during Phase 3A
calibration: any input containing the U+FFFD REPLACEMENT CHARACTER
came back from Ollama as a NaN-vector, and downstream cosine
similarity over a NaN vector is NaN — silently breaking retrieval
ranking. The same mojibake pattern is reachable in production any
time the user types or pastes text that round-tripped through a
mismatched codec, or any time a model-generated memory contains a
U+FFFD token (gemma4:e4b's en-dash output through Windows cp1252 is
the demonstrated repro).

**Hook point chosen.** Trait-default method on
`EmbeddingProvider::embed`. The required impl method is renamed to
`embed_raw`; the default `embed()` calls `sanitize_for_embed(text)`
and forwards to `embed_raw`. Public callers (`retrieval.rs`,
`backfill.rs`, `memory_service.rs`, tests) keep calling `.embed()`
unchanged. Sanitization is a single source of truth — every present
and future `EmbeddingProvider` impl (Ollama, Stub, Hf, plus any
candle-native follow-up under D-012) inherits it for free.

**Why not the other options.**
- *Standalone helper invoked at every call site.* Four call sites
  today, easy to miss the fifth — the failure mode of the missed
  call site is silent NaN, not a build error.
- *Sanitize at the upsert/write boundary only.* Misses the query
  path; a user-typed query carrying U+FFFD would still produce a
  NaN query vector and a wrecked retrieval.
- *Sanitize inside each provider impl.* Same drift risk as the
  standalone helper; trait default is strictly better.

**Sanitization shape.** `sanitize_for_embed(&str) -> Cow<'_, str>`:
returns `Cow::Borrowed(text)` when no U+FFFD is present (zero
allocation on the hot path — tested), otherwise `Cow::Owned` of
`text.replace('\u{FFFD}', " ")`. Replaced with ASCII space rather
than stripped, to preserve token boundaries the surrounding text
relies on.

**Scope held tight.** Only U+FFFD is scrubbed. Other zero-width and
non-character codepoints considered and explicitly excluded:
U+FEFF (BOM), U+200B–U+200F (ZWSP/ZWNJ/ZWJ/RTL/LTR marks),
U+2028/U+2029 (line/paragraph separators). None has a demonstrated
NaN-on-embed reproducer; widening now is speculation that silently
mutates user text. A regression test pins the narrow scope so any
future widening is a deliberate, reviewed change.

**Verification.** Six new unit tests in
`packages/l2-memory/src/embeddings.rs` (l2-memory test count rose
44 → 51 with `--features embeddings`):
1. Replaces U+FFFD with space in the Phase 3A repro shape.
2. Clean text returns `Cow::Borrowed` (no allocation).
3. Multiple U+FFFD all replaced.
4. Empty string borrowed.
5. Other zero-width codepoints (BOM, ZWJ, line separator) untouched
   — pins the narrow scope.
6. Trait-default `embed()` runs sanitization before reaching
   `embed_raw` (uses an in-test `CapturingProvider` to inspect what
   the provider actually saw).
7. Trait-default `embed()` passes clean text through unchanged.

`cargo test --workspace` green. `python tools/lint-memory-doc/check.py`
OK (122 anchors / 28 files).

**Did NOT modify** `apps/desktop/src-tauri/src/retrieval.rs` or
`apps/desktop/src-tauri/src/backfill.rs`. Trait-default approach
means the retrieval/backfill call sites pick up sanitization
without code changes. Other parallel agents own those files this
session.

---

## D-017 — Phase 3B F1: per-row retry-on-transient with exponential backoff (3 retries, base = pacing pause)

**Date.** 2026-04-25 (autonomous session, after D-013 stress-bench landed
the BACKFILL_STRESS_REPORT § "Headline numbers" 1.3 % HTTP 500 floor).

**Context.** D-013 measured a sustained ~1.3 % HTTP 500 failure rate
on Forge running bge-m3 through Ollama 0.21.2 at the 50 ms pacing
default, and showed that bumping to 100 ms reduced but did not
eliminate the cadence (failures cluster at ~50-row intervals,
suggesting an internal Ollama pressure boundary not addressable by
pacing alone). The pre-F1 backfill worker counted these as per-row
failures and continued — correct behavior, but the un-embedded
residue only got re-embedded on the next backfill invocation via
the Phase 2 `embedded_ids` skip-path. The §6 "proposed" addendum
to ADR-0007 D7 §Tuning notes flagged retry-on-500 with one
exponential-backoff retry as the natural F1 follow-up. F1 is now
landed; this entry documents the non-obvious schedule + counter
choices.

**Decision.**
1. **Retry budget = 3 (initial attempt + up to 3 retries = 4 total
   tries).** §6 of the stress report sketched "one retry"; F1
   landed three. Rationale: 1.3 % per attempt is large enough that
   one retry leaves a meaningful ~0.017 % residue, but three drops
   it to ~3 × 10⁻⁷ if attempts are independent. Independence is the
   weak link in that math (the 50-row cadence implies they are not
   independent), but the wall-clock cost of three retries is
   bounded — 50 + 100 + 200 = 350 ms added per *failed* row, which
   on Phase 3B's 13 failures is +4.55 s on a 4.71-min run. Cheap
   insurance.
2. **Exponential schedule, base = configured per-row pacing pause.**
   First retry waits `per_row_pause_ms`, doubles each subsequent
   retry. At the 50 ms default this is 50 / 100 / 200 ms; at a
   100 ms pause it would be 100 / 200 / 400 ms. Tying base to the
   pacing pause means a user who tuned pacing up because of queue
   pressure also tunes the backoff up — single knob, not two.
3. **Bounded, not unbounded.** Considered: backoff to N seconds,
   then declare host down. Rejected: the user-visible UX is "this
   row failed, the worker continued, you'll re-run later." Adding
   minute-scale stalls inside a single row obscures that contract.
   Three retries is the sweet spot between recovery rate and
   "worker is stuck."
4. **`recovered_failures` as a separate counter on `BackfillProgress`.**
   Considered: bump only `failures` or only `completed`. Rejected:
   conflating recoveries with un-retried successes hides the
   diagnostic signal that Ollama is under pressure; conflating
   them with permanent failures triggers UI false alarms ("X rows
   failed, re-run") for rows that already succeeded. Separate
   counter — increments once per recovered row regardless of how
   many of the 3 retries were consumed — gives the UI a clean
   "Y rows recovered after retry" line without double-counting
   `completed`. The post-run UX (F2) will surface this in a future
   commit; the field shipping ahead of the consumer is intentional
   so the wire shape is stable when F2 lands.
5. **4xx is never retried.** A `status code 4xx` substring on the
   embed error short-circuits the loop after one attempt. Bad
   model name, malformed body, oversize input — retrying just
   wastes wall-clock and clobbers the diagnostic signal.
   Implementation: classifier checks the 4xx prefix *before* the
   5xx / transport heuristics so a stray "transport: ... 400"
   takes the no-retry path.
6. **Cancel-respecting backoff.** The retry sleep cannot be a
   plain `std::thread::sleep` — that would extend the cancel-to-
   exit window from one row to one row + 200 ms in the worst case.
   Implemented as `cancel_aware_sleep`: chunked 10 ms polls of the
   cancel atomic, returns `false` immediately on flip. The
   `EmbedOutcome::CancelledDuringBackoff` arm exits without
   bumping any counter — the row was never finally decided, so
   counting it as a failure (or worse, a recovery) would lie.

**Alternatives considered & rejected.**
- **Restructure `EmbeddingProvider` error surface to carry HTTP
  status discretely** (replace `L2Error::Embedding(String)` with
  a structured variant). Rejected: massive blast radius across
  every L2 consumer; the string-classifier in `is_transient_embed_failure`
  is localised to the backfill worker and is regression-tested for
  the seven concrete Ollama error shapes that exist today. When
  the provider trait gets restructured for other reasons, the
  classifier collapses to a `match` over the new variant.
- **Skip-path on retry exhaustion (don't count as failure either).**
  Rejected: silently dropping rows would let the user think
  backfill completed when 1 % of their corpus is missing. The
  `failures` counter is the load-bearing signal — F2 surfaces it
  in the UI summary ("X rows failed; re-run if needed").
- **Global retry budget instead of per-row.** Rejected: a single
  Ollama hiccup that takes 50 rows down would consume the budget
  on the first burst and leave the rest of the run un-resilient.
  Per-row budget keeps each row independent.

**Verification.** Six new unit tests in `apps/desktop/src-tauri/src/backfill.rs::tests`:
1. `single_500_then_success_increments_recovered_count` — scripted
   embedder returns 500 once, then OK. Asserts `completed += 1`,
   `failures` unchanged, `recovered_failures += 1`, total of 2
   embed calls.
2. `three_500s_then_giveup_increments_failures` — scripted embedder
   returns 500 forever. Asserts `failures += 1`, `recovered_failures`
   unchanged, exactly `MAX_EMBED_RETRIES + 1` calls consumed.
3. `cancel_during_retry_backoff_exits_cleanly` — scripted 500;
   canceller thread flips the atomic during the 100 ms backoff
   sleep. Asserts `cancelled = true`, `failures = 0`, `completed = 0`,
   `recovered_failures = 0`, exactly 1 call.
4. `four_hundred_class_errors_not_retried` — scripted 400. Asserts
   `failures += 1` after exactly 1 call, no retries.
5. `classifier_recognises_5xx_timeout_and_refused_as_transient` —
   table test over 7 transient error shapes (500/502/503/504,
   read-timeout, connection-refused, dns-lookup-failed).
6. `classifier_rejects_4xx_and_payload_shape_errors` — table test
   over 6 terminal shapes (400/404/422, missing-array,
   non-numeric, empty-vector) plus `Storage` and `Internal`
   variants.

`cargo test --all-features` from `apps/desktop/src-tauri`: 283
passed (was 277 pre-F1, +6). `cargo test --workspace`: green.
`python tools/lint-policy-doc/check.py`: OK. `python tools/lint-memory-doc/check.py`: OK.

**ADR-0007 D7 §Tuning notes.** Ratified the §6 propose-only
addendum from BACKFILL_STRESS_REPORT in the same commit train
(separate `docs(adr)` commit). The §Tuning notes block now reads
"F1 landed in commit <hash>; sustained backfill recovers transient
failures via 3-retry exponential backoff; residual permanent
failures handled by Phase 2 `embedded_ids` skip-path on next
invocation."

**Files touched.**
- `apps/desktop/src-tauri/src/backfill.rs` — retry loop, classifier,
  cancel-aware sleep, scripted-embedder test scaffold, 6 tests.
- `apps/desktop/src-tauri/src/state.rs` — `BackfillProgress::recovered_failures: usize`.
- `docs/adr/ADR-0007-embeddings-onboarding.md` — D7 §Tuning notes
  ratification (separate commit).
- `planning/session_2026-04-25/DECISIONS_LOG.md` — this entry.

**Did NOT modify** `packages/l2-memory/src/embeddings.rs`
(parallel bge-m3 sanitization agent owns it; D-016) or
`apps/desktop/src-tauri/tests/` (parallel test-engineer agent
finding #2 owns it). All F1 tests live inline in
`backfill::tests` per the scope guard.

---

## D-018 — ADR-0010 ratification: Option B Accepted (production deferred), Option A Rejected

**Date:** 2026-04-25
**Trigger:** Don's autonomous-session brief authorised "land everything"
including ADR-0010 ratification; both Option A (recency-weighted combine)
and Option B (cross-encoder re-rank) implemented and benched against the
842-passage Phase 3A corpus.

**Outcome.**

| Metric    | Baseline | Option A | Option B |
| --------- | -------- | -------- | -------- |
| recall@1  | 0.6944   | 0.5278   | 0.7222   |
| recall@10 | 0.9028   | 0.9028   | 0.9306   |
| MRR       | 0.7755   | 0.6420   | 0.7920   |

- **Option A — Rejected.** Actively harmful: recall@1 −16.7 pp, MRR
  −13.4 pp. The Phase 3A miss-pattern analysis (D-015) predicted this
  precisely — the dominant failure mode is within-thread top-1 confusion,
  not recency bias, and on a corpus with monotonically ascending
  timestamps a recency weight biases toward late-thread rows that are
  systematically not the references. The combined-score helpers
  (`combined_rank_score`, `recency_decay`, `RECENCY_WEIGHT_ALPHA`,
  `RECENCY_HALF_LIFE`) stay in `retrieval.rs` with their unit tests as
  documented dead-end primitives for possible future tertiary use, but
  production Phase 4 is reverted to baseline cosine + strict-tiebreak.
- **Option B — Accepted in principle.** Real but modest lift: recall@1
  +2.8 pp, recall@10 +2.8 pp, MRR +1.6 pp. recall@3 regressed 1.4 pp
  (the reranker sometimes pushes correct candidates past rank-1 to
  rank-3+ then back out — bge-reranker-v2-m3 is not a perfect
  discriminator on the within-thread specificity failure mode). Smaller
  than the original ADR's "toward 90%+" hope but still the only direction
  that improved any metric.

**Why Option B's production wiring deferred to ADR-0011.**

The +2.8 pp recall@1 lift does not yet justify the engineering complexity
of a Reranker trait, AppState plumbing, `memory.json::retrieval.reranker.enabled`
config field, and Ollama / HF helper provider plumbing vs other M2
priorities. Three concrete triggers documented in ADR-0010 for re-opening:
(1) a re-bench on a more "real" corpus reproduces or amplifies the lift,
(2) a larger reranker (e.g. bge-reranker-v2.5-gemma2-lightweight) shows
>5 pp lift on the same corpus, or (3) a user-visible quality regression
in production retrieval makes the recall@1 floor a P1.

**What landed in this session.**
- `tools/hf_embed_helper/embed.py` — new `rerank` op (CrossEncoder
  via sentence-transformers); wire-shape stable.
- `apps/desktop/src-tauri/src/retrieval.rs` — Option A primitives
  (helpers + 4 unit tests) added then production rank reverted; net
  effect is the helpers are public + tested but not wired into
  `run_retrieval_context` Phase 4.
- `planning/session_2026-04-25/bench_recall_option_a.py` + JSON.
- `planning/session_2026-04-25/bench_recall_option_b.py` + JSON.
- `docs/adr/ADR-0010-rank-function-recency-weighted-combine.md` —
  Status flipped Proposed → Accepted, new §Empirical Validation
  section with all three result tables and the decision narrative.

**Verification.** `cargo test --all-features` from
`apps/desktop/src-tauri`: 293 passed, 0 failed (4 new Option-A-primitive
tests retained even after the production revert, since the helpers are
public). Bench scripts produce JSON outputs matching the documented
schema.

**Did NOT modify** `apps/desktop/src-tauri/src/backfill.rs`,
`apps/desktop/src-tauri/src/state.rs`, or `apps/desktop/src-tauri/tests/`
— parallel agents own those scopes per the autonomous-session brief.

---

## D-019 — `OLLAMA_FLASH_ATTENTION=false` confirmed as workaround for the Phase 3B 1.3% bge-m3 NaN failure rate

**Date:** 2026-04-25
**Context:** Phase 3B follow-up F3 (BACKFILL_STRESS_REPORT.md) called out `OLLAMA_FLASH_ATTENTION=false` as untested. Ollama issues #14657 and #9639 cite it as the canonical workaround for `failed to encode response: json: unsupported value: NaN` on F16 embedders. Don gave a 5-min budget to verify.

**Decision:** Workaround **CONFIRMED** for Aether's bge-m3 backfill workload. Recommendation: Don sets `OLLAMA_FLASH_ATTENTION=false` in his Ollama startup environment (system env var or Ollama service config). D-017's retry-with-backoff stays as belt-and-braces.

**Evidence.** Mini-bench: 13 previously-failing rows × 5 attempts = 65 embed calls, all 200, zero NaN-500s. Original run: same 13 inputs all 500'd at least once. Latency comparable (~140 ms vs original 181.8 ms mean). Restoration to default flags verified after the bench.

**Did NOT verify.** Full 1000-row regression with FA=false (out of 5-min budget). The 65/65 sample is sufficient to falsify "no effect" but not to prove zero failure rate at scale. Re-bench is cheap (~5 min) if/when operationally needed.

**Artifacts.**
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/bench_flash_attention_workaround.py
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/flash_attention_workaround_results.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/OLLAMA_UPSTREAM_BUG_REPORT.md (new "Workaround verification 2026-04-25" section)

## D-020 — Path A (broaden eval expectations) applied; 1 of 3 scenarios flipped, 1 stayed FAIL on a tenth paraphrase variant

**Context.** Don ratified Path A in
`planning/session_2026-04-25/EVAL_SCENARIO_BROADENING.md`: the eval
invariant becomes "Aurora behaves like Aurora-as-shipped" rather
than "Aurora emits a v1-stub literal token". This entry documents
what landed and what the re-run produced.

**Decision A — implementation shape.** The broadening doc specified
pattern SETS that the existing `requires` evaluator (case-insensitive
substring AND-of-all) would render unsatisfiable (e.g. requiring
both "forgot" AND "forgotten" AND "noted" simultaneously). Added a
new expectation kind `requires_any` to
`tools/evals/expectations.py`: case-insensitive regex alternation
that passes if ANY pattern matches. Additive and non-breaking — the
existing `requires` semantics are unchanged. Three failing scenarios
were rewritten to use `requires_any` with the verbatim per-scenario
pattern sets from the broadening doc §2 (modulo `\b` anchoring on
short tokens to avoid sub-word matches like "noted" hitting
"connoted"). See commit `aacee22`.

**Decision B — accept the surprise FAIL as data, not a defect.**
Memory scenario stayed FAIL because Aurora produced "Got it. Let's
leave that out of it." in this run, vs the Phase 7 baseline's
"Okay, let's put that aside." The broadening doc's nine-pattern set
was sized against the single Phase 7 sample and missed the
"leave (it|that) out" variant. Per the user's explicit instruction
("if a scenario unexpectedly stays FAIL, that's data — document,
don't pattern-hunt to make it pass"), no additional pattern was
added. The `forbids` set DID pass; Aurora behaved correctly. The
discrimination test — not the persona — is the gap.

**Re-run results.** 6 scenarios; 3 PASS / 2 FAIL / 1 SKIP. Delta vs
Phase 7: +1 PASS (`voice_transcription` flipped via referential
paraphrase match on "that concept"). Memory FAIL on tenth variant
(see Decision B). Vision FAIL as predicted by broadening doc §2.2 —
no `fridge_open.jpg` fixture, composer substitutes Aurora portrait,
no fridge-interior object class can match. Presence still SKIP — no
presence composer in V2.

**Outstanding action items** (full list in
`planning/session_2026-04-25/QUALITY_EVAL_V2_POST_REWRITE_REPORT.md`
§4):

1. Don commits `tools/evals/fixtures/fridge_open.jpg` → vision flips
   to PASS without further code change.
2. Aurora-strict canary suite (broadening doc §5) — deferred.
3. Capture N≥20 forget-scenario responses before any further
   pattern broadening; the single-sample fit was provably
   under-sized.
4. Presence composer — unchanged, deferred.

**Files touched:**
- `tools/evals/expectations.py` (new `requires_any` kind)
- `tools/evals/scenarios/memory_appropriateness/honors_forget.jsonl`
- `tools/evals/scenarios/vision_response_quality/describes_actual_scene.jsonl`
- `tools/evals/scenarios/voice_transcription/domain_vocab.jsonl`
- `planning/session_2026-04-25/quality_eval_v2_real_models_post_rewrite.json` (new)
- `planning/session_2026-04-25/quality_eval_v2_real_models_post_rewrite.md` (new)
- `planning/session_2026-04-25/QUALITY_EVAL_V2_POST_REWRITE_REPORT.md` (new)

**Scope guardrail.** `personas/aurora/persona.yaml` was NOT modified
(locked per PERSONA-SCHEMA §6). No retrieval / Ollama / planning JSON
files touched (parallel FLASH_ATTENTION agent owns that scope).
