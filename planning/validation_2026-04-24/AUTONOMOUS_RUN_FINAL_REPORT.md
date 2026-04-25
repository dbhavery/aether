# Autonomous Run Final Report — 2026-04-24

**Status at write time:** complete; tip `5ae531f` on `origin/dev`. Working tree clean. All tests green.

This report consolidates the full autonomous run that began with on-hardware validation and extended into implementation after Don granted further autonomy with full decision authority. It supersedes the earlier `VALIDATION_REPORT.md` (which only covers the first half) for the question "what landed in this autonomous window?"

---

## 1. By-the-numbers

| Metric | Start of run | End of run | Delta |
| --- | --- | --- | --- |
| Tip on `dev` | `eba8cd8` | `5ae531f` | **+24 commits** |
| `cargo test --all-features` (shell) | 265 / 265 | **275 / 275** | +10 (tier swap, backfill) |
| `vitest run` (apps/desktop) | 188 / 188 | **211 / 211** | +23 (Session B + backfill + toast + activeModel) |
| `python lint-memory-doc/check.py` | 100 anchors / 24 files | **112 / 25** | +12 anchors, +1 file (backfill.rs) |
| `tsc --noEmit` | clean | clean | unchanged |
| ADRs (Accepted) | 7 | **8** (ADR-0008 ratified + impl) | +1 |
| ADRs (Proposed) | 0 | **1** (ADR-0009 audit reach) | +1 |
| Tauri commands | 30+ | **34+** (backfill_status, backfill_count, start_backfill, cancel_backfill) | +4 |
| Frontend components | 24 | **27** (RetrievalTab, ReadinessIndicator, Toast, ToastContainer) | +3 (Toast pair counts as 2) |

---

## 2. Phase timeline

### Phase 1 — Validation (initial 12-hour window)

Hardware validation against Don's RTX 3090 Ti workstation. Surfaced ADR-0006 §4.C as critical defect (wgpu max_buffer_size unreliable). Tuned ADR-0007 D7 latency table with measured numbers. Shipped Session B scaffolds (typecheck-only stubs).

Commits: `a46ef28..174ad31` (8 commits).
Outcome: 5 ratification items queued for Don.

### Phase 2 — Implementation (extended autonomy)

Don ratified all 5 items mid-run with delegation of remaining decisions. Implementation cascade landed:

1. **ADR-0008 implementation** (`6038a28`) — broken tier heuristic replaced with `device_type + total_ram_gb` rule. ADR status flipped Proposed → Accepted same commit.
2. **Quality-Eval composition skip** (`8342068`) — instead of pattern-tuning per model, taught the eval harness to skip composition-dependent scenarios under `--backend ollama`. 4 false-failures became honest skips.
3. **Session B visual integration** (`8300d92`) — RetrievalTab landed as 4th tab in TrustDrawer; ReadinessIndicator wraps the Trust drawer button in the header.
4. **Backfill backend + UI + tests** (`a4c51f2`) — full ADR-0007 D5: orchestrator module, 4 Tauri commands, AppState atomics + progress shape, RetrievalTab integration with progress strip + cancel button.
5. **`tier:changed` event bus** (`20caa1d`) — ADR-0006 D5 follow-up retired. Tier-aware components re-read on event, no polling.
6. **Toast infrastructure** (`0a5dc69`) — ADR-0007 D6 transient toast on state transitions. Mounted at App root, polls readiness + listens for backfill done.
7. **ADR-0009 propose** (`4719512`) — formalised the carried-over Risk B (augmented-utterance audit reach) as a Proposed ADR. Cross-layer fix awaits Don.
8. **RetrievalTab tests** (`9164c62`) — 3 new tests for the backfill UI surfacing logic.
9. **activeModel display fix** (`90c5335`) — bug: UI showed tier-default model even when user had configured a different provider. Now reads memory_config.embeddings.provider in the UI.
10. **Provider hot-swap runtime** (`67e8c8e`) — bug: set_memory_config persisted new provider but didn't swap the runtime Arc. Now swaps for `ollama:` and bare-name prefixes.
11. **Provider hot-swap on boot** (`35ea921`) — companion fix: attach_memory_config_file now fires the same swap so persisted config is honored from boot.
12. **Handoff update** (`f5b8081`) — recorded the post-handoff extension and ratifications.
13. **Toast event tests** (`ff5d65d`) — 3 new tests for backfill done event branches.
14. **Clippy cleanups** (`130ad4a`) — minor backfill.rs warnings.
15. **activeModel UI tests** (`cf5b8f9`) — 3 new tests proving user-configured provider wins over tier default in the UI.
16. **MEMORY-V2 docs + rot-guard** (`5ae531f`) — §9 backfill subsection + 12 new anchors.

Commits: `6038a28..5ae531f` (16 commits).

---

## 3. Decisions ratified

All 5 action items from `HANDOFF_2026-04-24_M2_RUN_3_VALIDATION_COMPLETE.md` §2:

| Action | Decision | Status |
| --- | --- | --- |
| A. ADR-0008 (tier detection fix) | Accept | Implemented (commit `6038a28`); ADR status flipped to Accepted |
| B. Spark default substitution (nomic-embed-text) | Accept | Documented in ADR-0007 D7 §Tuning notes (no code change required) |
| C. Quality-Eval re-baseline approach | Don't re-baseline; implement composition-aware skip | Implemented (commit `8342068`) |
| D. Session B visual landings | Authority delegated; locked + shipped | Implemented across 3 commits |
| E. Add `lib.rs` to shell crate | Skip | DECISIONS_LOG D-002; held as future ergonomic improvement |

Plus the Spark default and ADR-0008 are both now in the `Accepted` shape rather than `Proposed`.

---

## 4. Bugs found and fixed during implementation

Two bugs surfaced from real hardware-validation work and were patched:

| Bug | Symptom | Fix commit |
| --- | --- | --- |
| RetrievalTab showed tier-default model regardless of user config | UI lied about which model was active | `90c5335` |
| `set_memory_config` persisted new provider but didn't swap runtime Arc | Readiness probe and embed calls used different models | `67e8c8e` + `35ea921` |

Both were silent — the validation surface caught them.

---

## 5. ADRs landed or proposed

| ADR | Status | Commits |
| --- | --- | --- |
| ADR-0006 (hardware tier model) | Accepted (cross-referenced ADR-0008 in §3) | `ff34e2f` |
| ADR-0007 (embeddings onboarding) | Accepted, D7 tuned | `fa1cc41` |
| **ADR-0008** (tier detection from device_type + RAM) | **Accepted** (was Proposed; implemented) | `a46ef28` (propose), `6038a28` (implement + accept) |
| **ADR-0009** (retrieval-augmented utterance audit reach) | **Proposed** (cross-layer; needs focused session) | `4719512` |

---

## 6. Risks status

| Risk | Status | Notes |
| --- | --- | --- |
| Tier auto-detection wrong by accident (D-004) | **RESOLVED** by ADR-0008 implementation | `6038a28` |
| Backfill rapid-fire Ollama 500 | **RESOLVED** by per-row pacing (50 ms default) in `backfill.rs` | `a4c51f2` |
| First-ever post-pull cold start 10× ADR estimate | DOCUMENTED in ADR-0007 D7 §Tuning notes | indicator copy already sets expectations |
| Augmented-utterance audit reach (Risk B from Session A) | DOCUMENTED in ADR-0009 (Proposed) | Implementation gated on Don ratification + cross-layer session |
| `set_tier` doesn't emit `tier_changed` | **RESOLVED** by `20caa1d` | Frontend subscribers in place |
| Heavy-usage protocol observed | RETIRED | This run was heavy-usage by design |

---

## 7. What's still open

For Don's review on return:

1. **ADR-0009 ratification + cross-layer session** — implementation requires touching L1 (TurnRequest shape) + L5 (audit row schema) + shell. Estimated 2-3 hr.
2. **HuggingFace embedder support** — not started. Would let `bge-small-en-v1.5` actually be the Spark default per ADR-0007 D7's original intent. Real ~150 LOC; touches packages/l4-router (cross-layer).
3. **NVML / IOKit feature gates for real VRAM** — held per ADR-0006 §Open items. RAM-only proxy (ADR-0008) gives correct answers for typical hardware; refinement is for users with low RAM + high VRAM (rare in 2026).
4. **Quality-Eval V2 composition support** — actually compose persona/memory/vision/voice into the eval prompt so the 4 currently-skipped scenarios become testable. Larger effort.
5. **Async backfill spawn** — replace sync `start_backfill` with a true tokio-spawned task once Tauri-managed `Arc<AppState>` is wired. Today's sync implementation is correct but blocks the IPC thread for the duration. `spawn_backfill` is already shaped in backfill.rs (marked `#[allow(dead_code)]`).
6. **`EmbeddingStore::embedded_ids(domain)` enumeration** — would let backfill skip already-embedded rows instead of brute-force re-embedding. Cross-layer (packages/l2-memory).

---

## 8. Doctrine compliance

- **One layer per session** (CLAUDE.md §1.3): observed throughout. No `packages/l*-*` modifications. All Rust changes confined to `apps/desktop/src-tauri/src/`. Cross-layer concerns (HF embedder, embedded_ids enumeration, ADR-0009 implementation) explicitly held for their own focused sessions.
- **Atomic small commits**: 24 commits average ~1 file change each, every commit independently revertable.
- **No destructive operations**: no force-pushes, no resets, no skipped hooks.
- **Heavy-usage protocol respected**: real model loads only during the validation phase; everything in the implementation phase is light-usage (compile + unit tests + stub embedders).

---

## 9. Acknowledged shortcuts and their rationale

For Don's review:

1. **Synchronous backfill execution** — blocks IPC thread for backfill duration. Acceptable for personal scale (<1000 rows in <60 s). Async refactor requires Tauri-managed `Arc<AppState>` plumbing, which is broader than this autonomous run should take on. `spawn_backfill` shape preserved in `backfill.rs` for future wiring.
2. **5-second polling for readiness in ToastContainer** — backend events would be cleaner but require AppHandle plumbed through `set_retrieval_readiness` call sites (broader refactor). Polling is correct and the latency cost is invisible.
3. **Brute-force re-embed in backfill** — re-embeds every row regardless of existing embedding. `upsert` is idempotent, so this is correct but wasteful. Skip-already-embedded requires `EmbeddingStore::embedded_ids` (cross-layer).
4. **No `lib.rs` in shell crate** (DECISIONS_LOG D-002) — would have made inspection tooling cleaner but is a real structural change. Held as a future improvement.

---

## 10. Final check matrix

```
cargo test --all-features (shell)         275 / 275  green
cargo test --workspace                    all green  unchanged
tsc --noEmit (apps/desktop)               clean      unchanged
vitest run (apps/desktop)                 211 / 211  green
python lint-memory-doc/check.py            OK 112/25  +12 anchors / +1 file
python lint-quality-doc/check.py          OK  60/19  unchanged
python tools/evals __main__.py --dry-run   6 / 0 / 0  unchanged
python tools/evals __main__.py --backend   2 / 0 / 4  composition-aware now
   ollama --no-capture                              (was 2 / 4 / 0)
git status                                clean
origin/dev tip                            5ae531f
```

---

## 11. Continuity for next session

The `HANDOFF_2026-04-24_M2_RUN_3_VALIDATION_COMPLETE.md` next-session prompt (§8 of that file) remains the canonical entry-point. Read this file second for the implementation context that landed AFTER the original handoff was authored.

If Don ratifies ADR-0009 on return, the cross-layer implementation session can start fresh from `5ae531f`. Otherwise, lighter follow-ups (HF embedder support, NVML feature gate, async-spawn refactor) can proceed in any order.

---

(end of autonomous run final report)
