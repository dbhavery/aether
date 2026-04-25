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
