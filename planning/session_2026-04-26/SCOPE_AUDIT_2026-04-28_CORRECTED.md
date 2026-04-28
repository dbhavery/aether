# Aether Full-Scope Audit — 2026-04-28 (CORRECTED)

**Written:** 2026-04-28 (verification pass by Term 2 against actual repo state).
**Supersedes:** `SCOPE_AUDIT_2026-04-28.md` for status claims; original kept verbatim for history.
**Branch:** `dev` at `6e4a509`. Working tree clean.
**Method:** Each workstream cross-checked against `git log`, file existence, and env state. Marked ✓ accurate, ✗ stale (with correction), or ? (further investigation).

---

## 1. Workstream snapshot — corrected

| # | Workstream | Original claim | Verdict | Actual state |
|---|---|---|---|---|
| A | Conversation training (V1→V4) | V4 prelaunch eval shipped; V4 LoRA queued | ✓ | Files present (see §2). Active session is writing `training/` — left untouched. |
| B | M2 Run 2 — retrieval wiring | 80% — submit_turn wiring pending | ✗ stale | **Already closed** in `9fad125`; hardened through `66fb51a`. See §3. |
| C | Vision track (companion build) | Commits "not on current dev branch tip" | ✗ stale | All 7 commits ARE on `dev`. See §4. |
| D | Quality-Eval V2 + Aurora discipline | 3/6 PASS; fridge fixture + 10th-paraphrase blocking 2 | ? | Scenario dirs all present; `fixtures/` dir does not exist (fridge blocker confirmed). 6/6 PASS not re-run (requires Ollama). See §5. |
| E | FLASH_ATTENTION env permanently set | Workaround verified; needs permanent set | ✓ | `OLLAMA_FLASH_ATTENTION` is empty in current shell — still unset on this machine. See §6. |
| F | Retrieval calibration at real-conv scale | 150-passage baseline only; 500-1000 synth queued | ✗ stale | **Real-corpus bench has landed.** See §7. |
| G | ADR-0011 cross-encoder production wire | Deferred until real conversation data | ✓ | No `docs/adr/ADR-0011*` file exists — consistent with "deferred". See §8. |
| H | Aurora-strict canary suite | Landed in `100a36f` | ✓ (typo fix) | Confirmed `100a36f` (audit's "100af36f" is a typo). Suite at `tools/evals/canaries/aurora_strict/`. See §9. |

---

## 2. Workstream A — V4 prelaunch eval (✓ accurate, files spot-verified)

Files present (read-only spot check; not opened to avoid colliding with active training session):

- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V4_PRELAUNCH_EVAL.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v3/scores_multi_discrim.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v3/scores_partial_3000.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v3/scores_raw_base.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v4/discriminator_multi/final/
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v4/discriminator_multi/training_meta.json

Per coordination rule, contents not inspected — V4 LoRA training in flight under `training/`.

---

## 3. Workstream B — M2 Run 2 (✗ stale → CLOSED)

Original audit:
> 80% — orchestrator built + 9/9 tests; **submit_turn wiring pending**

**Reality:** Wiring landed weeks before the audit was written. Verified at:

- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs (line 30 imports; lines 337–346 invoke `run_retrieval_context` → `format_retrieval_block` → `augment_utterance` inside `submit_turn`).
- Commits on `dev`: `9fad125` (wiring), `1f99a48` (TurnRequest split), `f378ea5` (audit row v2 with retrieval_provenance), `a8a7775` (label fix), `66fb51a` (e2e original-utterance survival test).

Closure note written to file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/M2_RUN_2_VERIFIED_CLOSED.md.

Implication: §10 Tier 3 item 7 ("M2 Run 2 wiring — requires fresh session") is also stale and should be removed from the todo. §7 (workstream F) deferral rationale "wait for orchestrator wiring" is unblocked.

---

## 4. Workstream C — Vision track (✗ stale → ALL ON DEV)

Original audit:
> the commits referenced (e.g. `cdf31f8`, `4ae9a13`, `dfb815b`) are **not on the current `dev` branch tip.** Either: live on a different branch / fork / rolled back / planned-but-not-shipped.

**Reality:** All 7 vision-track commits from the CONTINUE_COMPANION handoffs are on `dev`:

```
cdf31f8 feat(l4,apps/desktop): vision-capable provider behind analyze_frame
b94a613 docs(apps/desktop): document Tauri capability + media security model
3f3ba95 feat(apps/desktop): media-only filter on Trust drawer's History tab
4ae9a13 feat(l4): second vision provider — llama.cpp HTTP adapter
6257bd5 feat(apps/desktop): vision provider registry + runtime swap
3f19678 feat(apps/desktop): per-panel cue history for camera + screen
dfb815b docs: 2026-04-27 vision-strengthening reports + 2026-04-29 handoff
```

`git branch -a --contains cdf31f8` and `--contains dfb815b` both report `dev` and `remotes/origin/dev`. The vision track is **shipped**, not planned. Don's "clarify before next session" decision in §4 of the original is unnecessary — treat vision-track as already-done.

---

## 5. Workstream D — Quality-Eval V2 (? not re-run; structure ✓, fixture ✗ confirmed)

- 6 scenario dirs present under file:///C:/Users/dbhav/Projects/aether/tools/evals/scenarios/ : `chat_realism`, `memory_appropriateness`, `presence_aware_behavior`, `tool_use_judgment`, `vision_response_quality`, `voice_transcription`.
- `tools/evals/fixtures/` directory **does not exist** — `fridge_open.jpg` blocker confirmed real.
- Recent activity (`git log -- tools/evals/`): `aacee22 feat(evals): broaden 3 scenario expectations to match Aurora persona discipline (Path A)` followed by `100a36f` aurora canary. Suggests Path A broadening already landed; whether 3/6 → 5/6 holds today requires running `python tools/evals/__main__.py --backend ollama` (not run here — risks colliding with V4 training GPU usage and was outside scope of a verification pass).

Verdict ?: structural facts in audit hold; live PASS count not re-verified.

---

## 6. Workstream E — FLASH_ATTENTION env (✓ accurate)

`echo $OLLAMA_FLASH_ATTENTION` returns empty in current bash. Permanent env set has not happened since the audit was written. Don 5-min item still pending. (Setting it system-wide on Windows is Don's call — outside agent scope.)

---

## 7. Workstream F — Retrieval calibration at real-conv scale (✗ stale → LANDED)

Original audit:
> 150-passage baseline only; 500-1000 synthetic-corpus run **queued**

**Reality:** A real-corpus retrieval bench was executed and findings written:

- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/bench_real_corpus.py
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/real_corpus_recall.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/REAL_CORPUS_BENCH_FINDINGS.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/lexfridman.parquet (corpus: Lex Fridman ep 4, 417 Whisper segments)

Headline (per FINDINGS §TL;DR): bge-m3 ~18–28× better than random; the ground-truth metric is the problem, not the model. **ADR-0011 deferral is more justified, not less.** Plan C executed cleanly. The "queued" status in the original audit is wrong — this work shipped, and its conclusion strengthens §8's deferral.

---

## 8. Workstream G — ADR-0011 (✓ accurate)

`find docs/adr -name "*0011*"` returns nothing. Audit's "deferred" status matches actual repo state — no ADR file authored. Workstream F findings (§7 above) reinforce the deferral rationale.

---

## 9. Workstream H — Aurora canary suite (✓ accurate, minor typo)

- Commit `100a36f feat(evals): add aurora-strict canary suite (non-gating drift detector)` confirmed on `dev` (Don, 2026-04-25 21:43 PT).
- Suite location: file:///C:/Users/dbhav/Projects/aether/tools/evals/canaries/aurora_strict/
- Audit §1 row H lists "100a36f" but §10 item 9 also references the same; original §1 had a stray "100af36f" (extra `f`) — `100a36f` is the canonical sha.

---

## 10. Corrected todo list

Striking through items the verification invalidated:

### Tier 1 — autonomous-run targets (this session, training-arc)
1. **V4 LoRA training arc** — UNCHANGED. Active in other session under `training/`.
2. ~~Real-corpus retrieval calibration~~ — **DONE** (workstream F, §7). Remove.

### Tier 2 — Don decisions (5 min each)
3. Set `OLLAMA_FLASH_ATTENTION=false` permanently — **STILL PENDING** (verified empty in env).
4. Commit `tools/evals/fixtures/fridge_open.jpg` — **STILL PENDING** (fixtures dir absent).
5. Decide 10th-paraphrase memory-appropriateness scenario — UNCHANGED.
6. ~~Clarify workstream C status~~ — **NOT NEEDED**: all 7 vision commits are on `dev` (§4). Vision track is shipped.

### Tier 3 — next-session
7. ~~M2 Run 2 wiring~~ — **DONE** in `9fad125` (§3). Remove.
8. Comment on ollama#13572 — UNCHANGED.
9. Aurora-strict canary maintenance — UNCHANGED.

### Tier 4 — deferred
10. ADR-0011 production wire — DEFERRED, **further reinforced** by §7 findings.
11. ~~Retrieval calibration at real-conv scale~~ — **DONE** (§7). Remove.
12. V5 (full SFT or persona-conditioning) — UNCHANGED, awaits V4.

---

## 11. Process note

Two separate workstreams (B and F) and one fact about C were stale in the original audit. Common cause: it was written from handoff documents rather than from `git log` + filesystem. Future audits should diff handoffs against actual repo state before publishing — same lesson as the M2 Run 2 catch this morning.

(end of corrected audit)
