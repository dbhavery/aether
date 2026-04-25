# ADR-0009 Code Review — 2026-04-25

> Independent QA. Read-only review of commits `1f99a48`, `f378ea5`,
> `16a3db2`, `b577105` against ADR-0009 spec, `DECISIONS_LOG.md`
> D-001..D-005, and `CLAUDE.md` repo doctrine. Don was asleep during
> the autonomous session; this is the second pair of eyes.

---

## 1. Summary

**Verdict: PASS-with-notes.**

Implementation faithfully realises ADR-0009 Path A across all four
touched layers (L1 `TurnRequest`, L5 audit row + canonical seal, shell
`submit_turn` projection, frontend `AuditRow` renderer). The spec's
two-channel utterance contract is correctly enforced, schema-v1 wire
payloads round-trip implicitly, the HMAC envelope was extended to
cover the new fields (catching the only real "we'd ship a foot-gun"
bug before it landed), and the version-aware UI is honest about both
v1 ambiguity and v2 "retrieval ran but matched nothing". The three ADR
Open Items were not hand-waved — D-001 disposes of each with
defensible reasoning, and the "model-saw" deferral is locked by a
test that fails if a future renderer leaks the augmented string.

The notes are: (a) one minor doctrine wrinkle (TS mirror is hand-
authored against the §5 "Rust canonical, TS generated" rule, but
ts-bindings-gen is still scaffold-only repo-wide, so this is the
established pattern not a regression); (b) a missing
mixed-v1/v2-in-the-same-DB explicit integration test (round-trip
tests cover each in isolation, but no test reads a v1 row and a v2
row through the same `audit_recent` projection); (c) a small lint
gap on the read-side projection that copies `original_utterance` /
`retrieval_provenance` without checking `schema_version` first.

No blockers. Ratification commit was correct to flip Proposed →
Accepted given ADR §"Implementation note" + handoff quality
standard #8.

---

## 2. ADR-fidelity check (Decision-by-Decision)

| Decision | Spec | Implementation | Verdict |
|---|---|---|---|
| **1.** Audit truth = original utterance | L5 row records `original_utterance`, not model-input | `AuditRecordEvent.original_utterance: Option<String>`, populated by `engine.rs::write_audit` from `req.audit_extras.original_utterance` | PASS |
| **2.** Provenance as structured metadata on same row | `RetrievalProvenance { block_present, hits: Vec<RetrievedMemoryRef> }` field | Implemented exactly as specced. `block_present=false, hits=[]` correctly used as the "ran retrieval, matched nothing" sentinel (D-001 #1 resolution) | PASS |
| **3.** Transcript shape unchanged | Memory + transcript still record original | `submit_turn` continues to record `text` (the original) on the memory + transcript path; no diff to that surface | PASS |
| **4.** Router still receives augmented utterance | Shell composes `model_input_utterance = augment(block, original)`, L1 forwards it | `commands.rs::submit_turn` keeps `augment_utterance` and stamps `model_input_utterance: router_utterance`. `TurnEngine::handle_turn` calls `router.dispatch(..., &request.model_input_utterance, ...)` — captured-router test `allow_path_forwards_model_input_utterance_not_original` proves divergent channels | PASS |
| **5.** Pick Path A (split TurnRequest fields) | Add `original_utterance` + `model_input_utterance` to `TurnRequest` | Done. Legacy `utterance` field removed cleanly (D-003), eight call sites updated, hard compile-error chosen over silent `""` shim — correct reasoning | PASS |
| **6.** Migration via `schema_version: u32`, keep old rows as-is | v1 rows untouched, new rows stamped v2, UI surfaces version when relevant | `AUDIT_SCHEMA_VERSION_V1=1`/`_V2=2` constants, `#[serde(default = "default_schema_version_v1")]` resolver, `engine.rs::write_audit` always stamps V2, `AuditRow` shows "pre-ADR-0009" badge with explanatory tooltip on v1 rows | PASS |

**D-001 deviation.** D-001 corrects ADR §"Context"'s claim that the
v1 row stored the augmented utterance (it didn't — v1 had no
utterance field). The spec's user-visible bug ("audit-by-phrasing
search doesn't work") is still resolved, and the chosen v1→v2
migration path is strictly safer than the spec's framing implied.
Properly logged and rationalised in DECISIONS_LOG; not a
problematic departure.

---

## 3. Doctrine compliance findings

**§1.4 No cross-layer imports between sibling l\*** — PASS.
`turn.rs` imports `aether_l5_policy` (L1 → L5 via the canonical
policy boundary), which is allowed by §1.4 ("coordination happens
through `packages/l5-policy` typed outputs"). `RetrievalProvenance`
flows L5 → L1 (re-imported as `aether_l5_policy::RetrievalProvenance`)
which is the correct direction — L5 is the type owner. No L2
(memory) types appear in L5; the `domain` field is a `String` to
deliberately avoid an L5 → L2 dependency (audit.rs:62 comment is
correct).

**§1.5 Policy is single writer for side effects** — PASS. All audit
rows still flow through `engine.rs::write_audit`. The new
`audit_extras` channel is data-only; no shell or L1 code calls
`AuditStore::append` directly.

**§5 Events and types: Rust canonical, TS generated** — NOTE. New
TS types (`TrustRetrievalHit`, `TrustRetrievalProvenance`, fields on
`TrustAuditRow`) are hand-authored in `apps/desktop/src/lib/types.ts`.
`tools/ts-bindings-gen/` is README-only scaffold (no codegen
implementation yet), so this matches the established repo-wide
pattern rather than introducing drift. **Minor** — when ts-bindings-
gen lands, these types should be the first to migrate; until then,
the rot-guard anchor on `TrustAuditRow` field strings is the only
backstop.

**§4 Boundary tooling — `tools/lint-policy-doc/check.py` rot-guard** —
PASS. New file created (D-004); 25 anchors covering L1 fields, L5
fields/structs/constants, audit-seal coverage, shell wiring, and
frontend rendering. Anchor manifest is the right shape and matches
the pattern of `lint-memory-doc`/`lint-presence-doc`.

---

## 4. Test coverage findings

| Coverage area | Test | Status |
|---|---|---|
| L5: v1 wire payload (no fields) → v1 deserialize | `v1_payload_without_new_fields_deserializes_as_v1` | PASS — uses serde-strip technique to build a real v1 wire shape |
| L5: v2 row with rich provenance round-trip | `v2_row_with_provenance_round_trips_through_serde` | PASS — score fidelity asserted to 1e-6 |
| L5: v2 row with `None` provenance round-trip | `v2_row_without_provenance_round_trips_through_serde` | PASS |
| L5: HMAC seal covers new fields | Implicit via `make_row` populating `schema_version: V2`; existing chain tests would fail if the canonical payload omitted them | PASS but **MINOR gap** — no explicit "mutate `original_utterance` post-seal, verify chain breaks" tamper-detection test |
| L1: model_input forwarded, original held back | `allow_path_forwards_model_input_utterance_not_original` capturing-router fixture | PASS — exemplary, proves divergent channels |
| L5 → L1 audit_extras plumbing on Allow path | Existing `engine_slice.rs` constructors updated with `audit_extras: None` — but **GAP** — no test asserts that an `ActionRequest` with `Some(extras)` produces an audit row whose `original_utterance` matches | **MINOR gap** |
| Shell: submit_turn audit row contains original, not model_input | No direct integration test — the conversion happens in `submit_turn` and is only exercised end-to-end. Captured-router L1 test proves the L1 boundary; shell-side proof is implicit | **MAJOR-leaning-MINOR gap** |
| Mixed v1/v2 in same audit DB | No test reads back a stored v1 row alongside a stored v2 row through the same projection | **MINOR gap** — round-trip in isolation is covered, but a SQLite-backed test that inserts a hand-crafted v1 byte payload + a v2 row and projects both through `audit_recent` would close the loop |
| UI: v1 badge present, no headline | `v1 row shows the pre-ADR-0009 badge…` | PASS |
| UI: v2 hoists user text, hides badge | `v2 row hoists the user's text…` | PASS |
| UI: v2 disclosure summary copy | `v2 row exposes a model-saw disclosure…` | PASS |
| UI: v2 empty retrieval honest copy | `v2 row with empty retrieval reports 'nothing matched' honestly` | PASS |
| UI: v2 no provenance hides disclosure | `v2 row with no retrieval_provenance omits the model-saw disclosure entirely` | PASS |
| UI: never leaks model-input string | `v2 row never renders the augmented model-input string itself` — checks for "Relevant context (retrieval):" prefix | PASS — locks Open Item #3 deferral |

**Net.** Six well-targeted vitest cases, three Rust round-trip tests,
one capturing-router L1 test. Coverage is good; the only meaningful
holes are (a) mixed-version DB read-back and (b) end-to-end
"submit_turn → audit_recent" assertion that the original survives
the entire round trip in shape. Both are recommended follow-ups,
not blockers.

---

## 5. UI honesty audit

The handoff §2 quality standard #3 is "don't lie to the user". The
implementation passes:

- **v1 badge tooltip** (`TrustDrawer.tsx:357`): "Pre-2026-04-25
  audit schema. The user's exact phrasing is not recorded for this
  row; the row may include retrieval context that was prepended to
  the model input." Honest about both the absence (no phrasing
  recorded) and the historical pollution risk. The qualifier "may
  include" is correct because v1 rows had no utterance field at all
  (per D-001) — the row itself has no leak; the tooltip is hedging
  about the broader-system pre-ADR state.
- **v2 disclosure summary** (`TrustDrawer.tsx:401-405`): renders
  `"Aether also saw N memories from {domains}"` when
  `block_present=true`, OR `"Aether ran retrieval; nothing matched"`
  when `block_present=false`. Crucially does NOT silently omit the
  disclosure when retrieval ran-and-found-nothing — that distinction
  ("we asked, nothing came back" vs "we didn't ask") is preserved
  through to the user.
- **v2 disclosure absent** when `retrieval_provenance: None` —
  correct: no disclosure means no claim. A v2 conversation row
  where retrieval was never invoked won't render a misleading
  "nothing matched" line.
- **Per-hit breakdown** (`TrustDrawer.tsx:408-422`): renders
  `domain · memory_id (truncated) · score 0.XX`. No fabrication —
  every field comes from `RetrievedMemoryRef`. The middle-truncated
  `memory_id` keeps the full id in `title` for hover recovery.

**Honesty: PASS.** No surface lies to the user about what the row
recorded vs what was inferred.

---

## 6. Code quality findings

### MAJOR
None.

### MINOR

1. **`audit_recent` projection ignores `schema_version` when
   copying optionals** (`apps/desktop/src-tauri/src/commands.rs`
   ~L611–625). The Rust → TS projection unconditionally copies
   `r.original_utterance` and `r.retrieval_provenance` regardless of
   `r.schema_version`. In practice this is fine because v1 rows
   always have `None` for both fields (enforced by serde defaults),
   but a future writer bug that stamps `schema_version: V1` while
   populating `original_utterance` would silently leak through. A
   debug-assert (`debug_assert!(r.schema_version >= V2 ||
   r.original_utterance.is_none())`) or a normalising clamp would
   be defensive.

2. **`retrieval_provenance_for` allocates per-call** even when
   `hits.is_empty()`. For the empty-hits path (which is the common
   "retrieval bailed at deadline" case) the function still returns
   `RetrievalProvenance { block_present: false, hits: vec![] }`,
   which is one heap allocation per audit row even when there's
   nothing to record. Acceptable for current call volumes; revisit
   if conversation throughput climbs and audit becomes hot.

3. **`domain: format!("{:?}", h.domain).to_lowercase()`** — using
   `Debug` for a serialized wire field is fragile. If `MemoryDomain`
   ever gains a Debug impl that isn't the variant name (e.g. a
   `derive(Debug)` change to include fields), the audit-row domain
   string silently changes. A `Display` impl or an explicit
   `match`/`as_str()` method on `MemoryDomain` would be safer. The
   alternative — typing `domain` as `MemoryDomain` — was correctly
   rejected because L5 must not depend on L2 (audit.rs:62 comment).

4. **HMAC chain has no explicit tamper-detection test** for the
   new fields. The audit_seal canonical payload now includes
   `schema_version`, `original_utterance`, `retrieval_provenance`,
   so HMAC verification will fail if any of them is mutated post-
   write — but this is only proven implicitly by the bytes-changing.
   A `mutate_original_utterance_breaks_chain` test would lock the
   contract explicitly.

5. **`schema_version: u32`** — overkill width; `u8` or `u16`
   would be enough for any plausible version count. Cosmetic only;
   on-disk cost is negligible. Mentioned because a later "version
   namespacing" idea (e.g. major.minor) would benefit from picking
   the encoding now.

### NIT

6. **`TurnRequest.retrieval_provenance` clone in
   `turn.rs::handle_turn`** (line 237): `request.retrieval_provenance.clone()`
   is unavoidable because `request` is consumed by `handle_turn` and
   `audit_extras` needs an owned value, but the clone is the full
   `Vec<RetrievedMemoryRef>`. Could be moved instead of cloned by
   destructuring the request. Trivial.

7. **D-002 framing** — D-002 says `audit_extras` is a "small struct
   re-exported from `audit.rs`". It IS in `audit.rs` but is also
   re-exported from `lib.rs` — worth noting that the `policy_engine.rs`
   field type uses the `crate::audit::AuditExtras` path rather than
   the re-export, so the rot-guard anchor (which keys on
   `pub audit_extras: Option<crate::audit::AuditExtras>`) is tightly
   coupled to that exact import form. A future refactor that uses the
   re-export form would silently break the anchor.

---

## 7. Recommendations for follow-up commits

(Describe-only, per review constraint. Don to prioritise.)

1. **Add a SQLite-backed mixed-schema integration test.** Insert a
   hand-crafted v1 byte payload (no `schema_version` /
   `original_utterance` / `retrieval_provenance` fields on the wire)
   alongside a v2 row written through the engine's normal write path.
   Project both through `audit_recent` and assert: v1 row surfaces
   `schema_version=1` with both optionals `None`; v2 row surfaces
   `schema_version=2` with the populated fields. Closes the
   "explicit mixed-version DB" gap from §4.

2. **Add an end-to-end `submit_turn` shell test** that exercises a
   conversation turn with retrieval enabled, then reads back via
   `audit_recent` and asserts the audit row's `original_utterance`
   equals the user's text (NOT the augmented string). Closes the
   shell-side gap from §4.

3. **Add an HMAC tamper-detection test** that mutates
   `original_utterance` on a sealed row and asserts chain
   verification fails. Locks the audit_seal coverage explicitly
   rather than implicitly.

4. **Replace `format!("{:?}", h.domain).to_lowercase()`** with a
   `MemoryDomain::wire_name()` (or `as_str`) accessor on the L2
   side, then use that in `retrieval_provenance_for`. Removes the
   `Debug`-as-protocol fragility (§6 #3).

5. **Defensive clamp in `audit_recent` projection.** Either
   `debug_assert!` schema-version coherence or normalise: if
   `schema_version < V2`, force-`None` the v2 fields before
   projecting. Belt-and-suspenders against a future writer bug.

6. **(Optional) When ts-bindings-gen lands**, migrate
   `TrustRetrievalHit` / `TrustRetrievalProvenance` /
   `TrustAuditRow` to generated TS as a poster-child for the new
   pipeline. Until then, keep the rot-guard anchors on the field
   strings as the contract.

---

(end of review)
