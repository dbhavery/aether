# Execution Report — ADR-0005 Retrieval Wiring (Milestone 2 Run 2 final)

**Session date:** 2026-04-24 (continuation; calendar-accurate per current_status.py which sorts by commit time).
**Branch:** `dev`. Tip after push: `5b3ad94`.
**Input handoff:** `HANDOFF_2026-04-25_M2_RUN_2_PARTIAL.md` §6.
**Session type:** implementation (final wiring).

---

## 1. What shipped

Three commits, on top of `3ba40fc`:

| SHA | Subject |
| --- | --- |
| `3167850` | `feat(memory-config): add RetrievalConfig.max_items for ADR-0005 wiring` |
| `9fad125` | `feat(retrieval,commands): wire run_retrieval_context into submit_turn` |
| `5b3ad94` | `docs+test+rot(retrieval): close ADR-0005 — doc §10 step 8, anchors, e2e tests` |

Pushed to `origin/dev` at session end.

### Deviations from the prompt block

- **Integration path chosen: (b) with a twist.** The prompt recommended path (b) "call `run_retrieval_context` in the command handler, then pass augmented prompt / context to the router". Literally passing augmented prompt to the router requires either widening `TurnRequest` (cross-layer) or holding an `Arc<AppState>` inside the router (the Risk F ownership issue). The twist: `submit_turn` runs retrieval, then sets `TurnRequest.utterance = augmented_form` so the engine forwards the augmented string to the router. The ORIGINAL text is carried in parallel (`text` local, `PendingTurn::original_utterance`) and is what `user_record_raw` records in memory. Memory and transcript never see the retrieval block.
- **Prompt format picked.** Stable `Relevant context (retrieval):\n[N] <domain> <id>: <content>\n...` block, emitted by `format_retrieval_block`. Documented in the function's doc comment. Tests pin the ordering + separators.
- **`memory.json::retrieval` sub-object shape.** `{ max_items: u32 (default 5) }` under the same additive-on-read / unknown-fields-ignored contract as the `embeddings` block.
- **No `MemoryAwareRouter` / `RoleTaggedOllamaRouter` changes.** The router stays prompt-string-only; all retrieval composition happens one level up in `submit_turn`. This avoided the `Arc::new_cyclic` / `Weak<AppState>` gymnastics that path (a) would have required. Net effect is the same — the router forwards the augmented string to the provider.

### Files touched

- `apps/desktop/src-tauri/src/memory_config.rs` — `RetrievalConfig` struct, `MemoryConfig.retrieval` field, defaults, roundtrip test.
- `apps/desktop/src-tauri/src/retrieval.rs` — `format_retrieval_block`, `augment_utterance`, +6 tests (2 end-to-end composed).
- `apps/desktop/src-tauri/src/memory_router.rs` — `user_record_raw(session_id, utterance, ts_ms)`.
- `apps/desktop/src-tauri/src/state.rs` — `PendingTurn.original_utterance` field + two test sites updated.
- `apps/desktop/src-tauri/src/commands.rs` — retrieval call in `submit_turn`, `finalize_turn` / `provider_error_payload` gain `original_utterance: &str` param, `PendingTurn` record gains the field, `resolve_approval` threads it through.
- `apps/desktop/src-tauri/src/main.rs` + `memory_service.rs` — passive `cargo fmt` changes (mod ordering, multi-line chain).
- `tools/lint-memory-doc/check.py` — 9 new anchors.
- `docs/MEMORY-V2-ARCHITECTURE.md` — §10 step 8 documenting the wiring.

---

## 2. Check matrix

| Check | Result | Delta |
| --- | --- | --- |
| `git status` | clean | — |
| Commits ahead of `origin/dev` | 0 (pushed) | — |
| `cargo fmt --all -- --check` | clean | — |
| `cargo check --all-features` (shell) | clean | — |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings" --test sqlite_session` | 23 / 23 | unchanged |
| `apps/desktop/src-tauri cargo test --all-features` | **230 / 230** | +7 (was 223) |
| `cargo test --workspace` | all green | — |
| `python tools/lint-memory-doc/check.py` | **OK 79 / 19** | +9 anchors, +3 files |
| `python tools/lint-quality-doc/check.py` | OK 60 / 19 | unchanged |
| `tools/evals --dry-run` | 6 / 6 | — |

---

## 3. Risks retired / still open

- **A (NEW → RETIRED).** Retrieval is now live on real turns. `submit_turn` calls `run_retrieval_context` before `engine.handle_turn`; embeddings.enabled=true + seeded Durable rows produce a `Relevant context (retrieval):` block the router forwards. Pinned by `end_to_end_determinism_when_embeddings_off` + `end_to_end_augments_when_embeddings_on_with_hits`.
- **B (CARRIED).** `gemma4:e4b` + `bge-m3` still unverified on real hardware.
- **F (NEW 2026-04-24 → SIDESTEPPED).** `AppState::build_active` ownership issue never mattered — the chosen integration path doesn't require an `Arc<AppState>` inside the router.
- **E (CARRIED).** Projects / Artifacts / Facts / Preferences still alias Session.

---

## 4. Notes for future work

- The augmented-utterance-in-`TurnRequest` approach is simple but means the L1 engine's audit trail sees the augmented form. If that becomes a problem (e.g. for a future audit dashboard that shows raw user input), the fix is to widen `TurnRequest` with `retrieval_context: Option<String>` — a small L1 change that would now be clearly scoped.
- The rank-order test uses the stub embedder; real embedding providers may produce different score distributions. The top-K cap + recency tiebreak is deterministic regardless.
- `augment_utterance` puts retrieval BEFORE the user message. If feedback shows this pushes the model's attention wrong, the alternative (retrieval-as-system-message) would require widening the router API or TurnRequest.

---

(end of report)
