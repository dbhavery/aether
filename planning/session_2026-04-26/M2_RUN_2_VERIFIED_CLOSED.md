# M2 Run 2 — Verified Closed

**Date:** 2026-04-28
**Branch:** `dev` at `6e4a509`

The M2 Run 2 retrieval orchestrator wiring listed as "80% — submit_turn wiring pending" in `SCOPE_AUDIT_2026-04-28.md` §1 / §3 was already shipped before that audit was written. Wiring landed in `9fad125 feat(retrieval,commands): wire run_retrieval_context into submit_turn`, hardened through `1f99a48` (split `TurnRequest` into `original_utterance` + `model_input_utterance`), `f378ea5` (audit row v2 with `retrieval_provenance`), `a8a7775` (stable `MemoryDomain::label()` in provenance), and `66fb51a` (e2e test asserting the original utterance survives `submit_turn → audit_recent`). Production turn-dispatch path now invokes `run_retrieval_context` → `format_retrieval_block` → `augment_utterance` (apps/desktop/src-tauri/src/commands.rs:337–346). No code commit needed; M2 Run 2 closed.
