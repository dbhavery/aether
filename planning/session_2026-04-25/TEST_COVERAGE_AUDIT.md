# Test Coverage Audit — Aether (2026-04-25)

**Branch:** `dev` &nbsp;|&nbsp; **Tip audited:** `a9a55cf` &nbsp;|&nbsp; **Mode:** read-only static analysis
**Baselines (per handoff):** cargo `275/275` (apps/desktop/src-tauri); vitest `211/211` (apps/desktop); workspace cargo green
**Author:** Test Engineer agent (autonomous session)

---

## 1. Executive summary — top 5 risks

| # | Risk | Severity | Where |
|---|------|----------|-------|
| 1 | **52 Tauri commands, only ~3 exercised by name in `commands.rs` test bodies.** Wrappers are thin, but the IPC contract (arg coercion, `State<'_, AppState>` lifetime, `AppHandle` event emission, error stringification) is unverified end-to-end. A wire-shape rename or a panic in a command body becomes a silent boot-time crash for the UI. | **HIGH** | apps/desktop/src-tauri/src/commands.rs |
| 2 | **No serde round-trip tests for `TurnRequest`, `BackfillProgress`, `RetrievalProvenance`.** Audit row v1/v2 has compat tests (good), but the live wire-shapes the frontend consumes do not. Any rename or field removal silently breaks TS bindings without a test red. | **HIGH** | packages/l1-interaction/src/turn.rs:67; apps/desktop/src-tauri/src/state.rs:242; packages/l5-policy/src/audit.rs:78 |
| 3 | **Backfill double-start guard untested.** `start_backfill` returns `Err("backfill already in progress")` (commands.rs:2353); no test asserts a second invocation while a worker holds the flag rejects. Also no test for "submit_turn races backfill" (concurrent embedder lock contention). | **HIGH** | apps/desktop/src-tauri/src/backfill.rs; commands.rs:2344 |
| 4 | **`ReadinessIndicator` only tests 3 of 4 `kind` states + 0 of 5 `NotReadyReason` sub-variants.** `unknown` rendering is implicit; `embed_failed`, `bailout`, `low_disk` differentiated copy is untested. | **MEDIUM** | apps/desktop/src/components/ReadinessIndicator.test.tsx (4 it blocks); types.ts:508 |
| 5 | **14 frontend components ship without test files** — including `ApprovalModal`, `SettingsDrawer`, `ToastContainer`, `Header`, `InputBar`. ToastContainer is the polling consumer of the new ADR-0009 toast events; a regression there silently swallows backfill-done notifications. | **MEDIUM** | apps/desktop/src/components/ |

---

## 2. By-package coverage matrix

Counts derived from `grep #[test]` against `src/` (inline) and `tests/` (integration). "Public API" gap is heuristic from reading `lib.rs` exports vs. tested surfaces.

| Package | inline `#[test]` | integration test fns | Coverage gaps | Risk |
|---|---:|---:|---|---|
| `event-bus` | 1 | 0 | Only `source_layer_round_trips`. No tests for cross-layer event ordering invariants stated in CLAUDE.md §5 (`change_id`, monotonic `seq`). | MEDIUM |
| `l1-interaction` | 0 | 8 | Solid `turn_slice` happy/deny/ask + `model_input_utterance` forwarding. **Missing:** TurnRequest serde round-trip; oversized utterance; concurrent submit_turn behavior. | MEDIUM |
| `l2-memory` | 37 | 24 | Strong unit + integration on sqlite/embeddings. **Missing:** `EmbeddingStore::embedded_ids` enumeration semantics on empty/full/partial states; embedding store crash recovery (truncated files). | LOW |
| `l3-presence` | 22 | 2 | Heavy unit, thin integration. Presence config rotation untested across process restart. | LOW |
| `l4-router` | 96 | 1 | Excellent provider-level coverage (Ollama, llamacpp, whispercpp). **Missing:** integration test exercising router→provider error-typing across the trait boundary; HF embedder is unscaffolded (per HANDOFF §4C). | LOW |
| `l5-policy` | 26 | 31 | Best-tested package — audit seal, engine slice, sqlite backends. **Gap:** retrieval-provenance attached to ASK/DENY paths (only ALLOW v2 round-trip is asserted). | LOW |
| `l5-policy-ts` | 0 | 0 | TS package — relies on type-checking; no behavioral tests for decision deserialization. | MEDIUM |
| `l6-persona` | 7 | 9 | Adequate. Persona pack YAML loader covered; rare-case bad-YAML coverage unverified. | LOW |
| `l7-trust` | 8 | 1 | Minimal. **Missing:** integration test for the full audit row → Trust drawer rendering chain. | MEDIUM |
| `media-engine` | 0 | 0 | **Scaffold only** (80 LOC). No tests. Acceptable while empty; flag if it grows. | LOW |
| `storage` | 5 | 3 | Migration sequence untested across a full apply-rollback-reapply (single-writer rule from CLAUDE.md §6 unverified under contention). | MEDIUM |
| `telemetry` | 1 | 0 | **Scaffold** (52 LOC). | LOW |
| `types` | 0 | 0 | TS index only. N/A. | LOW |
| `ui-kit` | 0 | 0 | TS tokens. N/A. | LOW |

### Tauri-shell module breakdown (`apps/desktop/src-tauri/src/`)

| File | LOC | inline tests | Notable gaps |
|---|---:|---:|---|
| `adapter.rs` | 84 | 0 | Adapter glue — likely thin enough to skip, but verify no logic. |
| `backfill.rs` | 653 | 9 | **Missing:** double-start rejection; concurrent submit_turn vs backfill embedder contention; cancel-during-final-row race; AppHandle emission failure path. |
| `commands.rs` | 3,383 | 37 | 37 inline tests, but ~3 reference command names directly. Most coverage is helper/parser-level (utterance validation, frame validation, verb routing). See §3. |
| `hardware.rs` | 392 | 7 | Snapshot serde round-trip covered. |
| `idle_probe.rs` | 274 | 4 | Thin; idle-detect failure path should be checked. |
| `main.rs` | 452 | 0 | App-init wiring untested by design. |
| `media_permissions.rs` | 345 | 10 | Solid. |
| `memory_config.rs` | 417 | 12 | Solid. |
| `memory_router.rs` | 374 | 4 | **Thin.** Routing decision matrix between domains under-covered relative to module size. |
| `memory_service.rs` | 1,919 | 35 | Heavy file, decent count, but ratio (~1 test per 55 LOC) is the lowest excluding `commands.rs`. |
| `mic_permissions.rs` | 281 | 10 | Solid. |
| `presence_config.rs` | 272 | 9 | Solid. |
| `provider.rs` | 50 | 0 | Trivial. |
| `retrieval.rs` | 987 | 27 | Well-covered. **Missing:** rank tie-break stability across reruns; `fetch_one` failure mid-pipeline. |
| `state.rs` | 2,548 | 29 | Lock-poison recovery untested (every `.expect("...lock")` is an unverified panic path — see §5). |
| `tier.rs` | 391 | 17 | Solid; ADR-0008 covered. |
| `vision_cache.rs` | 410 | 16 | Solid. |
| `vision_registry.rs` | 937 | 26 | Solid; persistence round-trips covered. |
| `voice_registry.rs` | 909 | 26 | Solid; persistence round-trips covered. |

---

## 3. Tauri commands without direct happy-path tests

52 commands defined; `grep`-cross-reference of command names inside the `#[cfg(test)]` region of `commands.rs` shows direct invocation by name for **3** (`analyze_frame`, `switch_persona`, `transcribe_utterance`). The other 49 rely on indirect coverage of helpers they wrap.

**Caveat:** thin wrappers around well-tested helpers (e.g., `backfill_count` → `estimate_unembedded_count`) are low-risk. The list below ranks the wrappers whose body contains *non-trivial logic* (state mutation, branch, error stringification) that lacks a name-level test.

### High-risk untested wrappers

- `start_backfill` (commands.rs:2344) — owns the double-start guard, cancel-flag reset, `next_ts` job-id generation, AppHandle plumbing. None of these branches verified by name.
- `submit_turn` (commands.rs:308) — orchestrates retrieval, provider call, audit emission. Helpers tested; the orchestration glue is not.
- `resolve_approval` (commands.rs:431) — approval-ticket state machine entry point.
- `clear_session` (commands.rs:537) — destructive op; touches AppHandle event emission.
- `redetect_hardware` (commands.rs:2273) — re-runs ADR-0008 detection live.
- `set_active_vision_model` / `set_active_speech_model` / `set_active_vision_provider` / `set_active_speech_provider` — hot-swap paths; the 2026-04-24 run cited a silent activeModel bug here.
- `memory_forget_item_after_approval` / `memory_edit_after_approval` — approval-gated state transitions.
- `set_memory_config` / `set_presence_config` / `set_tier` — config-write paths that fan out to runtime-effect side channels.
- `cancel_backfill` (commands.rs:2376) — branches on in-progress flag; one branch unverified.
- `forget_older_than_days` (commands.rs:247) — destructive sweep; bound-checking of negative/zero days unclear.

### Lower-risk untested wrappers (pure read pass-through)

`companion_banner`, `list_personas`, `current_autonomy_preset`, `presence_current`, `presence_status`, `presence_recent_history`, `memory_recent`, `memory_list`, `audit_recent`, `telemetry_recent`, `telemetry_clear`, `get_media_permissions`, `get_mic_permission`, `get_memory_config`, `get_presence_config`, `get_tier`, `vision_status`, `voice_status`, `list_vision_providers`, `list_vision_models`, `refresh_vision_models`, `list_speech_providers`, `list_speech_models`, `refresh_speech_models`, `embeddings_readiness`, `backfill_status`, `backfill_count`, `set_autonomy_preset`, `switch_persona` (some coverage), `set_media_permission`, `set_mic_permission`, `memory_forget`, `memory_forget_item`, `memory_edit`, `analyze_frame` (some coverage), `transcribe_utterance` (some coverage).

**Total Tauri commands lacking a direct name-level test: 49 / 52.**

---

## 4. Frontend components without test files

Listing per `ls *.tsx` minus `*.test.tsx`:

| Component | LOC class | Risk |
|---|---|---|
| `ApprovalModal.tsx` | medium | **HIGH** — approval flow is policy-critical |
| `CameraPanel.tsx` | medium | MEDIUM — captures frames into analyze_frame |
| `CueHistoryStrip.tsx` | small | LOW |
| `Disclosure.tsx` | small | LOW (utility) |
| `Header.tsx` | small | MEDIUM — hosts ReadinessIndicator + global state |
| `InputBar.tsx` | medium | **HIGH** — user-text entry, hotkey handling |
| `PersonaCard.tsx` | small | LOW |
| `PresenceDot.tsx` | small | LOW |
| `PresetPicker.tsx` | small | MEDIUM — autonomy preset selection |
| `ProviderBadge.tsx` | small | LOW |
| `ScreenPanel.tsx` | medium | MEDIUM — screen capture |
| `SettingsDrawer.tsx` | large | **HIGH** — host of many config surfaces |
| `ToastContainer.tsx` | medium | **HIGH** — polling consumer of backfill-done events (per HANDOFF §7.3) |
| `VoicePanel.tsx` | medium | MEDIUM — utterance capture |

**Total components without test files: 14 / 28.**

---

## 5. Panic-prone paths in production

Counts via `grep -E '\.unwrap\(\)|\.expect\(|panic!|todo!|unimplemented!'` on the pre-`#[cfg(test)]` region of each file:

| File | Production count | Notes |
|---|---:|---|
| `state.rs` | 49 | All observed are `.expect("...lock")` on `RwLock` / `Mutex`. Lock poisoning recovery untested. |
| `commands.rs` | 20 | Mostly mutex-lock expects. |
| `memory_service.rs` | 10 | Mostly lock expects. |
| `backfill.rs` | 12 | All `.expect("backfill progress lock")` / `.expect("active read lock")`. |
| `vision_registry.rs` | 12 | All registry RwLock expects. |
| `voice_registry.rs` | 12 | All registry RwLock expects. |
| `retrieval.rs` | 3 | Targeted expects worth re-reading: lines 1–986 (sample reads inconclusive — verify before recommending). |
| `main.rs` | 1 | Boot-time expect; acceptable. |

**Pattern observed:** the project uses `.expect("…lock")` on every internal lock acquisition. This is idiomatic Rust but means a single poisoned lock crashes the IPC backend with no recovery. **There is no test that simulates a poisoned lock** (e.g., a panicked thread inside a write guard). This is a class-level gap, not a per-line bug.

**No `todo!()`, `unimplemented!()`, or `panic!()` were found in any production region** — good hygiene.

**Sampled lines (state.rs):**
- state.rs:597 `let mut w = self.vision.write().expect("vision registry write lock");`
- state.rs:744 `let mut w = self.voice.write().expect("voice registry write lock");`
- state.rs:837 `*self.media_permissions.write().expect("perm write lock") = loaded;`

**Sampled lines (backfill.rs):**
- backfill.rs:191 `let mut p = state.backfill_progress.lock().expect("backfill progress lock");`
- backfill.rs:242 `.expect("embedding provider read lock")`

---

## 6. Recommended next-tests (ordered by risk-reduction)

### Tier A — write before next ADR

1. **`backfill_double_start_returns_err`** — drive `start_backfill` twice in succession, assert second call returns `Err("backfill already in progress")`. Owner: `backfill.rs`. Effort: 15 min.
2. **`turn_request_round_trips_through_serde_with_split_utterance_fields`** — round-trip ADR-0009 `TurnRequest` shape (`original_utterance` + `model_input_utterance`). Mirror the audit_seal v2 round-trip pattern. Owner: `packages/l1-interaction/tests/`. Effort: 20 min.
3. **`backfill_progress_round_trips_through_serde`** — frontend consumes this; rename = silent break. Owner: new test in `state.rs` test mod. Effort: 10 min.
4. **`readiness_indicator_renders_each_not_ready_reason_distinctly`** — assert distinct copy for `embed_failed`, `bailout`, `low_disk`, plus `unknown` state rendering. Owner: `ReadinessIndicator.test.tsx`. Effort: 30 min.

### Tier B — write before next milestone close

5. **`toast_container_consumes_backfill_done_event_and_dismisses`** — covers the polling contract for the ADR-0009 toast surface. Owner: new `ToastContainer.test.tsx`. Effort: 30 min.
6. **`approval_modal_resolve_emits_correct_decision`** — covers the policy-critical modal surface. Owner: new `ApprovalModal.test.tsx`. Effort: 30 min.
7. **`submit_turn_during_backfill_does_not_deadlock`** — concurrency test in tokio runtime; spawn a worker, fire `submit_turn` mid-flight, assert both complete. Owner: `backfill.rs` test mod (tokio multi-thread). Effort: 1 hr.
8. **`set_active_vision_model_updates_active_label_observed_by_status`** — guards against the activeModel display drift bug from 2026-04-24. Owner: `commands.rs` test mod. Effort: 30 min.
9. **Parameterized happy-path command smoke test** — single test that constructs a tiny `AppState`, walks every read-only command, asserts no panic + serializable output. Catches lock-poisoning panic at boot. Owner: `commands.rs`. Effort: 1 hr.

### Tier C — nice-to-have

10. **`embedding_store_recovers_from_truncated_index`** — file-corruption resilience for `FlatFileEmbeddingStore`. Effort: 1 hr.
11. **`audit_provenance_attached_on_ask_and_deny_paths`** — extend the v2 round-trip to non-ALLOW decisions. Effort: 30 min.
12. **`storage_migration_apply_rollback_reapply_idempotent`** — migration discipline. Effort: 1 hr.
13. **`input_bar_handles_paste_and_submit_hotkey`** — covers `InputBar.tsx`. Effort: 30 min.
14. **`settings_drawer_persists_changed_config_on_close`** — covers `SettingsDrawer.tsx`. Effort: 1 hr.
15. **`event_bus_seq_monotonic_under_concurrent_emit`** — verifies CLAUDE.md §5 invariant. Effort: 1 hr.

---

## 7. What's already well-covered (avoid duplication)

- **Audit row schema v1 ↔ v2 compatibility** — `packages/l5-policy/tests/audit_seal.rs` lines 170–280 cover v1 deserialization + v2 with/without provenance round-trips. Excellent.
- **Backfill worker happy paths + cancel + skip-already-embedded** — 9 inline tests covering completion, in-progress flag reset, cancellation, and second-pass skipping (including partial pre-embedded sets).
- **Provider trait round-trips** — every provider in `packages/l4-router/src/providers/` (Ollama, llamacpp, whispercpp + vision variants) has `set_model_round_trips_and_label_reflects_new_model` + chat round-trip.
- **Audit seal tampering detection** — payload tamper, key tamper, head rollback all covered.
- **Frame and utterance data-URL validation** — 13 inline tests across the validate_* helpers in `commands.rs` cover scheme, MIME, separator, body length edges.
- **Verb-routing parser** — every verb (read/write/edit/delete/shell/browse) has a routing test plus a case-insensitivity test.
- **Tier detection (ADR-0008)** — 17 inline tests in `tier.rs`.
- **Persistence round-trips for vision + voice registries** — both active selection and per-model map persistence.
- **Engine slice (l5-policy)** — 13 integration tests covering allow/deny/ask/defer, grant TTL, emergency revoke, audit-before-allow ordering.
- **TurnRequest model_input_utterance forwarding** — `allow_path_forwards_model_input_utterance_not_original` covers the ADR-0009 plumbing at L1.

---

## 8. Methodology + caveats

- **Static analysis only.** No `cargo test` or `vitest run` was executed. Counts may include `#[ignore]`d tests.
- **"Direct command test" heuristic** = grep of command identifier inside the file's `#[cfg(test)]` region. A test that constructs a command's body via a private helper *without naming the command* will not be detected. This biases the audit toward over-reporting gaps; manual review of any specific command should precede a "no test exists" claim per `MEMORY.md` "Before recommending from memory" rule.
- **Wire-shape gap inference** assumes that absence of a `round_trips` test name = absence of round-trip coverage. Verified against `audit.rs` (positive), `turn.rs` (negative — confirmed gap), `state.rs::BackfillProgress` (negative — confirmed gap).
- **"Lock poisoning untested"** is a class-level claim — no `std::panic::catch_unwind` + lock-acquire pattern appears anywhere in the test corpus.
- **Frontend component count** is by file presence, not behavior. Some sibling test files exercise multiple components; these are not credited here.

---

## 9. Boundary-lint coverage

Lint tools at `tools/lint-*/` cover the Rust↔TS contract via doc anchors:
- `lint-memory-doc`: 112 anchors / 25 docs (per HANDOFF baseline).
- `lint-quality-doc`: 60 / 19.
- Vision/voice/policy/presence lint docs exist; anchor counts not enumerated this pass.

**Gap:** no audit lint covers the `commands.rs` IPC surface itself. A new command added without a test is invisible to CI today. Recommend a lightweight `lint-tauri-cmd-coverage` that fails when a `#[tauri::command]` lacks a matching `#[test]` referencing its name (or an explicit `// no-test-required: <reason>` waiver).

---

## 10. Reference paths

- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/TEST_COVERAGE_AUDIT.md (this file)
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/backfill.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/state.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/retrieval.rs
- file:///C:/Users/dbhav/Projects/aether/packages/l1-interaction/src/turn.rs
- file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit.rs
- file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/tests/audit_seal.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/

(end of audit)
