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

## D-007 — ADR-0006 §6 ratification: `OLLAMA_MAX_LOADED_MODELS` surfaced as Forge tier-tunable

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
