# Security Review — Session 2026-04-25 (autonomous run)

> Read-only review of commits `1f99a48 … ad6a457` plus the trailing `a9a55cf` review-doc commit (10 commits, 8 source-bearing). Threat model: [planning/13_trust_security_redteam.md](file:///C:/Users/dbhav/Projects/aether/planning/13_trust_security_redteam.md). Repo rules: [CLAUDE.md](file:///C:/Users/dbhav/Projects/aether/CLAUDE.md).
>
> Scope: ADR-0009 v2 audit rows (utterance + retrieval provenance), L1 TurnRequest split, embedded-id skip path, multi-model VRAM bench, several docs commits.

---

## 1. Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| **HIGH** | **1** |
| MEDIUM | 2 |
| LOW | 3 |
| NIT | 1 |
| VERIFIED-SAFE | 12 |

**Verdict: NEEDS-FIX (one HIGH).** The audit hash-chain integrity guarantee is silently broken for any pre-existing sealed v1 row. Everything else is clean or defense-in-depth.

The core ADR-0009 surface — XSS in the audit UI, capability gating, memory-poisoning paths via backfill, prompt-injection through stored utterances — is solid. The Trust drawer renders all attacker-controllable strings as React text nodes (no `dangerouslySetInnerHTML` anywhere in `apps/desktop/src`), the L5 capability gate still fronts every shell command, and the new `embedded_ids` path is in-memory only with no disk traversal. The single HIGH is a migration-safety oversight in `audit_seal.rs::CanonicalAuditPayload`.

---

## 2. Findings

### HIGH-1 — Audit hash-chain verification breaks for pre-ADR-0009 sealed rows

- **Dimension:** Audit log integrity (#3) + Migration safety (#10)
- **File:** [file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit_seal.rs](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit_seal.rs) lines 178–223
- **Threat-model link:** §"Red-team focus areas / 7. Logging / audit completeness" — *log tampering, replay failures*.
- **Description:** Commit `f378ea5` extends `CanonicalAuditPayload` with three new fields (`schema_version`, `original_utterance`, `retrieval_provenance`). All `AuditRecordEvent` payloads on disk now hash through this widened canonical form. For a row sealed BEFORE this commit, the original `record_hmac` was computed over the OLD canonical payload (without these fields). Verifying that legacy row post-deploy:
  1. Deserializes `schema_version` to `1` via `serde(default)`. (correct)
  2. Recomputes `canonical_bytes` with `schema_version: 1, original_utterance: None, retrieval_provenance: None` included.
  3. Produces a SHA-256 over a strict superset of the original bytes → different `event_hash` → different HMAC → `AuditVerifyError`.

  Net effect: the very first chain verification after deploying `f378ea5` against an existing `aether_audit.db` will report tampering on every legacy row, even though the DB is untouched. This both (a) creates false-positive tamper alerts for legitimate users and (b) gives an actual attacker cover — every chain that includes legacy rows already fails, so a real splice in the v1 region is indistinguishable from the migration noise. Tests added in `tests/audit_seal.rs` only cover deserialization round-trips, not chain re-verification across the schema boundary.
- **Mitigation factors:**
  - `audit_seal` is `#[cfg(feature = "sqlite-backend")]` and not in the default OSS preview build. Personal-scale dev installs running stock features don't hit this.
  - The chain itself is still tamper-evident under the new schema; the issue is purely a one-way break at the v1→v2 transition row.
- **Recommendation:** One of:
  1. **Version-aware canonicalization (preferred).** Branch on `schema_version` inside `From<&AuditRecordEvent>` — for `schema_version == 1`, omit the three new fields from the serialized struct entirely so legacy rows hash to the same bytes they did pre-ADR. Add a regression test that seals a row with the pre-f378ea5 canonical shape, then verifies it under the post-f378ea5 verifier.
  2. **One-shot re-seal migration.** On startup, if the chain fails to verify and every failure is in `schema_version == 1` rows, re-seal the v1 segment with the new canonicalization under the existing key, persist a migration marker. Invasive; only worth it if there are deployed user-facing audit DBs.
  3. **Document the break.** If the OSS preview has zero legacy DBs (likely for a pre-1.0 product), add an explicit migration ADR + DB-version gate that refuses to load v1 chains and forces a fresh DB. Simplest, but loses history.

### MEDIUM-1 — `RetrievedMemoryRef::domain` derived from `format!("{:?}", h.domain).to_lowercase()`

- **Dimension:** Audit row integrity / information disclosure (#7)
- **File:** [file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs) lines ~295–304 (`retrieval_provenance_for`)
- **Description:** The shell builds the audit-row's `domain` string with `format!("{:?}", h.domain)` (Rust `Debug` formatter), then lowercases. If `MemoryDomain` ever gains a tuple/struct variant, the Debug output silently changes shape (e.g. `"durable"` → `"durable(\"foo\")"`) and the audit row's stable-search contract breaks without a compile error. Display vs Debug discipline.
- **Recommendation:** Add an explicit `MemoryDomain::label()` (already exists per `domain.label()` use in `backfill.rs`) and call that here. Two lines. Also pin via a unit test that asserts the four expected lowercase strings.

### MEDIUM-2 — `RetrievalProvenance::hits` is unbounded on the audit row

- **Dimension:** Resource exhaustion (#5) / audit-log volume
- **File:** [file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit.rs](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit.rs) `RetrievalProvenance` (lines ~62–73)
- **Description:** `hits` is a `Vec<RetrievedMemoryRef>` with no length cap. The orchestrator's `top_k` is bounded today (5 per the retrieval spec), but the audit row contract doesn't enforce that — a future orchestrator change to `k=500` would silently 100× audit-row size. Memory IDs and float scores are small but the cumulative effect on `aether_audit.db` size is real, and on the JSON HMAC-canonicalization path it's wasted CPU.
- **Recommendation:** Either document a hard cap in the type doc (e.g. "writers MUST trim to ≤16 hits before stamping") and assert in `engine.rs::write_audit`, or clamp inside `retrieval_provenance_for` at the shell.

### LOW-1 — `score.toFixed(2)` on NaN/Inf renders `"NaN"`/`"Infinity"` in the audit UI

- **Dimension:** Information disclosure (#7) / UI robustness
- **File:** [file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/TrustDrawer.tsx](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/TrustDrawer.tsx) `AuditRow` provenance list (≈line 410)
- **Description:** If a future ranker produces a non-finite score (currently impossible — cosine similarity is bounded — but no static guarantee), the audit row renders the literal string `"NaN"` next to a memory id. Not exploitable, just ugly and slightly debug-leaky.
- **Recommendation:** `Number.isFinite(h.score) ? h.score.toFixed(2) : "—"`.

### LOW-2 — Backfill skip walk emits one progress event per skipped row

- **Dimension:** Resource exhaustion (#5)
- **File:** [file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/backfill.rs](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/backfill.rs) lines 270–276
- **Description:** Skip path calls `emit_progress` per row. For N=100k pre-embedded memories the worker fires 100k Tauri events at native walk speed (no `pause`). Frontend bus + IPC churn. Not a security vuln; a perf footgun for users on large memory stores. Consumer-side coalescing isn't established here.
- **Recommendation:** Coalesce progress emissions on the skip path (e.g. every 100 skips or every 50 ms). Out-of-scope for this milestone; track as Forge-tier perf follow-up.

### LOW-3 — Skipped count merges into `processed = completed + skipped` for the progress bar but stays separate in the summary

- **Dimension:** Information disclosure (#7) — audit-log clarity
- **File:** [file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/backfill.rs](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/backfill.rs) doc-comment + commit `de34217` body
- **Description:** Per the commit message, the progress bar treats `processed = completed + skipped_already_embedded` while the summary text reports them distinctly. This is a deliberate UX choice and documented; calling it out as a LOW so a future reader doesn't "fix" the apparent inconsistency. Not a security finding.
- **Recommendation:** Add a one-line comment next to the JS progress-bar consumer pointing back to the `BackfillProgress` doc. (Frontend file in this commit set is small.)

### NIT-1 — `audit_seal.rs` doc still describes the v1 canonical payload shape

- **Dimension:** Documentation drift
- **File:** [file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit_seal.rs](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit_seal.rs) module docstring §"Sealing model"
- **Description:** Module doc enumerates fields covered by the seal but doesn't mention the new ADR-0009 v2 fields. The struct comment at line 192 calls them out, but the high-level sealing-model doc didn't get the equivalent update.
- **Recommendation:** Add a single bullet to §"What this protects" — "ADR-0009 v2 fields (`schema_version`, `original_utterance`, `retrieval_provenance`) are part of the canonical payload and inherit the same tamper-evident guarantee."

---

## 3. Verified-safe items

For each, I read the relevant code or commit diff and concluded no issue:

1. **XSS in `AuditRow` (TrustDrawer.tsx).** All attacker-controllable fields (`row.original_utterance`, `h.memory_id`, `h.domain`) render as React text children. No `dangerouslySetInnerHTML` anywhere under `apps/desktop/src` (confirmed via Grep on the whole tree). The `<details>/<summary>` block is JSX-rendered. (Threat #1.)
2. **Quotation marks** around the user utterance use `&ldquo;` / `&rdquo;` — those are HTML entities in source; React encodes them as Unicode code points before insertion as text, no parsing context.
3. **`title={h.memory_id}` attribute.** React's prop encoding handles `"` and `<` correctly; can't break out into an attribute injection.
4. **TurnRequest split (`1f99a48`).** Hard compile-error policy on legacy `utterance` field is the safer migration. No silent default that produces audit rows reading "user said nothing".
5. **L1 engine forwards `model_input_utterance` to the router** ([turn.rs:233](file:///C:/Users/dbhav/Projects/aether/packages/l1-interaction/src/turn.rs)) and `original_utterance` to `AuditExtras`. Reproducibility-truth and audit-truth are correctly bifurcated.
6. **Capability gate not bypassed.** `submit_turn` → `engine.handle_turn(...)` → `policy.evaluate(...)` is unchanged; the new audit fields are handed in via `audit_extras` and read inside `write_audit`, which only fires after the policy decision has been computed. No new code path skips the gate.
7. **Backfill capability gate.** `run_backfill_worker` still routes through `Capability::RetrievalContext` — the skip-path change in `de34217` is purely inside the per-row loop, downstream of the capability check.
8. **`embedded_ids` resource bound.** `FlatFileEmbeddingStore::embedded_ids` returns one `MemoryId` per stored embedding row in the requested domain. Bound = number of rows the user themself has embedded. No attacker amplification: writes are local. `HashSet<MemoryId>` is `O(N)` memory but N is the user's own corpus — same constraint that already applies to the upsert map.
9. **Path traversal on `embedded_ids`.** Implementation is `guard.rows.get(&domain).map(...)` — pure in-memory map probe, no filesystem walk. JSONL persistence is round-tripped through the existing `with_persistence` load path, which was not changed in this commit set.
10. **Cancel during skip walk.** The cancel flag is checked at the head of every per-row iteration *before* the skip-decision branch ([backfill.rs:265–269](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/backfill.rs)). Test `worker_cancel_during_skip_walk_still_marks_cancelled` enforces it. Double-cancel is a no-op (atomic store-true). Cancel during teardown is impossible — `finalize` sets `backfill_in_progress=false` before `backfill_cancel.store(false, ...)`, but a second worker invocation re-initializes `BackfillProgress` from scratch (lines 188–199).
11. **HMAC seal covers the v2 fields going forward.** New rows hash through `CanonicalAuditPayload` which includes `schema_version`, `original_utterance`, and `retrieval_provenance`. Mutating `original_utterance` post-write would change the recomputed hash. (See HIGH-1 for the migration caveat.)
12. **No Isabelle leakage.** Grep for `Isabelle|isabelle` over the touched files (`commands.rs`, `backfill.rs`, `retrieval.rs`, `audit.rs`, `turn.rs`, `TrustDrawer.tsx`) yields exactly one hit — a pre-existing comment on the `privileged_profile` field in `audit.rs` that predates this session. No new content tagged Isabelle in any commit. CLAUDE.md §1.6 satisfied.

---

## 4. Out-of-scope follow-ups

- **Prompt-injection via `original_utterance` shown in the audit UI.** The string is rendered as a React text node (safe today), but it's also the field a future "search audit by phrasing" feature will likely run free-text queries against. If any future surface lands that re-renders this string into an HTML context (markdown panel, copy-to-clipboard with HTML payload, AI summarization that quotes back), the renderer needs an explicit safe-text contract. Out of scope for this commit set — flag for the search-audit-by-phrasing ADR.
- **Memory poisoning via `retrieval_provenance.hits[].domain`.** Today the domain is stamped from the orchestrator's known enum and is closed-set. If `RetrievedMemoryRef::domain: String` ever starts accepting provider-supplied or scraped-content-supplied domain labels, memory poisoning class #2 in the threat model becomes a live concern (an attacker controls a label that downstream UIs trust). Lock the domain field to a closed enum at the L5 boundary in a follow-up.
- **Length-cap on `original_utterance`.** No cap is enforced. A 10 MB user utterance lands in audit, in the canonical hash, and in the UI. Today the L1 engine doesn't run on adversarial input, but Wave-5 voice/transcribe paths will. Add a writer-side cap (e.g. 64 KB; truncate-with-marker) in a follow-up; document in ADR-0009 §Open items.
- **Multi-model VRAM bench (`cb668ad`).** The Phase-3C bench is a Python tool under `planning/`; no source code is shipped. No security review needed beyond confirming it doesn't write outside its session dir (it doesn't).

---

## 5. Cross-reference to threat-model items

| Threat-model section ([13_trust_security_redteam.md](file:///C:/Users/dbhav/Projects/aether/planning/13_trust_security_redteam.md)) | Coverage in this review |
|---|---|
| §1 Prompt attacks | XSS surface in TrustDrawer audit UI verified safe (#1, #2, #3). Out-of-scope follow-up flagged for future search-by-phrasing rendering. |
| §2 Memory poisoning | `embedded_ids` skip path verified non-amplifying (#8). Closed-set `domain` flagged as out-of-scope follow-up. |
| §4 File / data exfiltration | `RetrievalProvenance::hits` unbounded — MEDIUM-2. Length cap on `original_utterance` flagged out-of-scope. |
| §5 Permission bypass | Capability gate verified intact for `submit_turn` and `run_backfill_worker` (#6, #7). |
| §7 Logging / audit completeness | **HIGH-1 — chain verification breaks across v1→v2 schema boundary.** New fields covered by HMAC going forward (#11). |
| §8 Failure and recovery | Backfill cancel + atomics verified (#10). |

End. (~485 lines budgeted; ~470 actual.)
