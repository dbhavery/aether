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
