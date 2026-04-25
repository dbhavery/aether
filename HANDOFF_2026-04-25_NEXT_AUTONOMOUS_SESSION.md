# Handoff — 2026-04-25 → Next Autonomous Session

**Written:** 2026-04-25 at the close of the prior 2026-04-24 autonomous run.
**Branch:** `dev`. Tip at handoff: `993c6fb`. All commits pushed. Working tree clean.
**Authority for next session:** Don has delegated **all-level decision authority** including cross-layer. Full GPU VRAM available. Multi-hour window with Don asleep.
**Quality posture:** **Quality-first.** Where a knob exists that trades quality for resource efficiency, the default is the quality-preserving setting. Surface resource pressure to the user; never absorb silently.
**Tool authority:** Use any skill, tool, or web research to answer UI/UX questions before deciding. Research-backed defaults beat instinct.

---

## 1. State at handoff (read this first)

### 1.1 Verified tip

```
git log --oneline -5
993c6fb docs(validation): final report consolidating the full autonomous run
5ae531f docs(memory-v2): add §9 backfill subsection + 12 new rot-guard anchors
cf5b8f9 test(frontend): activeModel resolution paths in RetrievalTab UI
130ad4a chore(backfill): clippy cleanups
ff5d65d test(frontend): ToastContainer backfill-done event branches
```

### 1.2 Check matrix (post-this-run baseline)

| Check | Result |
| --- | --- |
| `cargo test --all-features` (apps/desktop/src-tauri) | **275 / 275** |
| `cargo test --workspace` (packages) | all green (small counts; mostly scaffolds) |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings" --test sqlite_session` | 23 / 23 |
| `tsc --noEmit` (apps/desktop) | clean |
| `vitest run` (apps/desktop) | **211 / 211** |
| `python tools/lint-memory-doc/check.py` | OK 112 / 25 |
| `python tools/lint-quality-doc/check.py` | OK 60 / 19 |
| `python tools/evals __main__.py --dry-run` | 6 / 0 / 0 |
| `python tools/evals __main__.py --backend ollama` | 2 / 0 / 4 (composition-aware skip per the 2026-04-24 fix) |

### 1.3 What just shipped (compressed; full detail in `planning/validation_2026-04-24/AUTONOMOUS_RUN_FINAL_REPORT.md`)

- ADR-0008 (tier detection from `device_type + total_ram_gb`) — Accepted + implemented.
- ADR-0009 (retrieval-augmented utterance audit reach) — **Accepted 2026-04-25** (implemented + ratified in the autonomous session this handoff opened; tip `b577105` on `dev`). Audit row at schema v2 with `original_utterance` + `retrieval_provenance`; `TurnRequest` carries split `original_utterance` / `model_input_utterance`.
- Backfill backend + RetrievalTab UI integration with progress + cancel.
- `tier:changed` event bus (ADR-0006 D5 follow-up retired).
- Toast infrastructure for ADR-0007 D6 transition surfacing.
- Provider hot-swap (runtime + boot) — silently broken behavior fixed: UI no longer lies about the active embedding model.
- Quality-Eval `--backend ollama` now skips composition-dependent scenarios honestly instead of false-failing.
- 12 new rot-guard anchors covering the backfill module, Tauri command surface, and progress shape.

---

## 2. Quality-first decision standards (locked)

These supersede any default in case of conflict.

1. **Indistinguishable-from-human bar applies to every modality.** Voice, text, presence, retrieval-as-recall — they all serve the impression that the user is talking to a person who remembers.
2. **Calibrated confidence > overconfident wrongness.** Hedge correctly. If the model isn't sure, the response should reflect that.
3. **Don't lie to the user.** The activeModel display fix this run is the canonical instance. Any UI that shows what the system is doing must match what the system is actually doing.
4. **Surface resource pressure; never silently absorb.** Best-effort + visible warning posture per ADR-0007 §Decision 1. Never silently degrade fidelity to fit a budget.
5. **One layer per session WAS the rule; this session OPENS that.** Don has delegated cross-layer authority for this autonomous window. Cross-layer changes are now permitted but should be **focused** (ADR-0009 implementation IS one focused change touching three layers; "while I'm here, also fix X in unrelated layer Y" is not).
6. **Heavy-usage is permitted.** Real model loads, real VRAM allocation, real GPU work. Stay within Don's hardware envelope; don't OOM the box.
7. **Atomic small commits.** No mega-commits. Each commit independently revertable, message ≥ 1 paragraph of why.
8. **Ratify ADRs as you implement them.** If you implement ADR-0009, flip its status from Proposed → Accepted in the same commit.

---

## 3. GPU-heavy work queue (use the wide-open VRAM)

Ranked by user-visible impact:

### 3A. Real-corpus retrieval calibration at scale (HIGH VALUE)

**Goal:** Validate the retrieval rank function against a 500–1000-passage synthetic corpus with known semantic ground truth. The 2026-04-24 validation Block 5 used 150 passages — representative but small. At realistic-conversation scale (a few months of Aether use ~ 500-2000 turns), rank quality may degrade.

**Procedure:**
1. Generate a synthetic conversation corpus using `gemma4:e4b`. Prompt the model to produce 50–100 conversational threads, each 10–20 turns, with deliberate cross-thread referential structure ("the trip planning we discussed last week", "your sourdough recipe", etc.). Save as JSONL with ground-truth rank pairs.
2. Embed with bge-m3 (Flame default).
3. Re-run the existing `bench_long_context.py` against the new corpus.
4. Measure recall@1/3/5/10/20, MRR, and rank correlation.
5. If rank quality drops materially below the 150-passage baseline (95% r@1 on bge-m3), the rank function in `apps/desktop/src-tauri/src/retrieval.rs::run_retrieval_context` may need a recency-weighted combine instead of pure cosine + recency-tiebreak. Open an ADR proposing the new shape.

**Heavy-usage cost:** ~15-30 min embed time for 1000 passages on bge-m3.

### 3B. Sustained backfill stress test (HIGH VALUE)

**Goal:** Validate the backfill pacing-pause solves the rapid-fire 500 Don's hardware surfaced. Run a real 1000-row backfill end-to-end. Measure VRAM creep, throughput drift, queue behavior over 3+ minutes.

**Procedure:**
1. Seed `apps/desktop/src-tauri` test harness with a 1000-row Durable history (use a one-off integration test).
2. Trigger the backfill via `start_backfill` Tauri command from a CLI test driver.
3. Capture VRAM snapshots every 10 seconds via Ollama `/api/ps`.
4. Validate `BackfillProgress::completed` reaches 1000, `failures == 0`, `cancelled == false`.
5. Document the end-to-end wall-clock against the 3-min projection in ADR-0007 D7 §Tuning notes.

**Heavy-usage cost:** ~3-5 min sustained bge-m3 embed.

### 3C. Multi-model coexistence ceiling test (MEDIUM VALUE)

**Goal:** Map Don's actual VRAM ceiling. Block 4 of the prior run loaded 3 models in 12.15 GB; the 3090 Ti has 24 GB. What's the realistic 4th/5th model that can co-reside? Useful for the future avatar VRAM reservation in ADR-0006 §6.

**Procedure:**
1. Load gemma4:e4b + bge-m3 + nomic-embed-text (baseline 12 GB).
2. Add gemma4:26b — what VRAM tips? Does Ollama evict?
3. Capture per-model VRAM, total resident, eviction events.
4. Update ADR-0006 §6 reservations with measured headroom data.

**Heavy-usage cost:** ~10-20 GB resident at peak; 5-10 min wall-clock.

### 3D. Quality-Eval V2 composition support (LARGE; consider deferring)

**Goal:** Implement persona/memory/vision/voice composition in the eval harness so the 4 currently-skipped scenarios become testable. Re-run all 6 scenarios.

**Scope:** Touches `tools/evals/__main__.py` significantly. Persona compile path; memory injection; vision frame fixture loading; voice transcription stubbing. Real ~300 LOC + a new `composition.py` module. Then heavy-usage re-runs.

**Decision:** propose if you have time; defer if calibration (3A) + stress (3B) + cross-layer (4A) take the session.

### 3E. First-session live UX QA (HIGH VALUE — visual research-backed)

**Goal:** Actually launch the dev build, click through the new RetrievalTab + ReadinessIndicator + Toast surfaces, take screenshots, document UX gaps.

**Procedure:**
1. `npm run tauri dev` from `apps/desktop`.
2. Trigger every state in the readiness state machine via memory.json edits + Ollama daemon kill/restart.
3. Use the `windows-app-pilot` skill (or `playwright-cli` if web-shell) to take screenshots of each state.
4. Use the `frontend-design-review` skill to evaluate against the three pillars: frictionless, distinctive, design-system-compliant.
5. Document gaps in a new `planning/validation_2026-04-25/UX_AUDIT.md`.

**Heavy-usage cost:** small. Mostly UI interaction time.

---

## 4. Cross-layer work queue (now permitted)

Don has delegated cross-layer authority. Each item below is one focused change. Do not bundle.

### 4A. ADR-0009 implementation (HIGHEST PRIORITY among cross-layer)

**Effort:** ~2-3 hr focused session.
**Touches:** `packages/l1-interaction` (TurnRequest shape), `packages/l5-policy` (audit row schema bump v1 → v2), `apps/desktop/src-tauri/src/commands.rs::submit_turn` (field plumbing), `apps/desktop/src/components/TrustDrawer.tsx::AuditList` (version-aware rendering).

**Ratification:** flip ADR-0009 status from `Proposed` → `Accepted` in the same commit as the implementation per quality standard #8.

**Validates:** users can finally search audit by their actual phrasing without retrieval-block pollution.

### 4B. `EmbeddingStore::embedded_ids(domain)` enumeration

**Effort:** ~30 min.
**Touches:** `packages/l2-memory/src/embeddings.rs` (trait + FlatFileEmbeddingStore impl). Backfill module (`apps/desktop/src-tauri/src/backfill.rs`) gains a smarter "skip already-embedded" path.

**Validates:** backfill no longer brute-force re-embeds. Sustained 1000-row backfill (3B) becomes a 1-row backfill on the second invocation.

### 4C. HuggingFace embedder provider

**Effort:** ~3-4 hr.
**Touches:** `packages/l4-router` (provider plumbing), `packages/l2-memory` (HF provider impl matching `EmbeddingProvider` trait), `apps/desktop/src-tauri/src/state.rs::swap_embedding_provider_for_config` (extend the `hf:` arm).

**Validates:** `bge-small-en-v1.5` actually loadable as the Spark default per ADR-0007 D7's original intent. DECISIONS_LOG D-001 substitution (nomic-embed-text) becomes optional rather than forced.

### 4D. Async backfill spawn (small but breaks current sync caveat)

**Effort:** ~1 hr.
**Touches:** `apps/desktop/src-tauri/src/main.rs` (Tauri-managed `Arc<AppState>` registration), `apps/desktop/src-tauri/src/commands.rs::start_backfill` (returns immediately with job id; spawns the worker on tokio).

**Validates:** backfill UI progress strip actually animates instead of frozen-spinner-then-pop. The `spawn_backfill` shape in `backfill.rs` is already there waiting for the Arc plumbing.

---

## 5. UI research targets (use research skills)

Before making any visual decision in this session, research the established pattern. The 2026-04-24 run validated this approach (D2 dot placement, D3 toast-vs-no-toast both research-backed).

### 5A. Audit row UI (relevant if 4A lands)

The Trust drawer's existing `AuditList` is text-heavy. With ADR-0009's new fields (`original_utterance`, `model_input_utterance`, `retrieval_provenance`), what's the right rendering?

Research targets:
- Linear's audit log UX
- Notion's "see who edited what" surface
- GitHub's PR review timeline
- Carbon Design System's "activity log" pattern

Question to answer: how should an entry differentiate "what the user said" from "what the model saw" without bloating the row?

### 5B. Long-form progress UI (relevant for backfill)

Current backfill progress is a simple bar + text. For 3-min runs, users may want richer status: rate, ETA, current domain breakdown.

Research targets:
- Docker Desktop's image-pull progress
- Steam's game-install progress
- Homebrew's terminal progress (translated to GUI)

Question: at 3 min, what status detail keeps users informed without anxiety?

### 5C. Multi-model status surface (if 3C reveals VRAM pressure)

If multi-model coexistence shows real-world VRAM pressure, Aether may want to surface "X / Y GB VRAM in use" somewhere.

Research targets:
- LM Studio's status bar (recently REGRESSED — note from 2026-04-24 research)
- Ollama Desktop's resource indicator
- Activity Monitor / Task Manager patterns

Question: where does this live? Header chip? Settings drawer? Trust drawer System tab?

---

## 6. Paste-verbatim next-session prompt

````md
You are Claude Code, opening Aether for a long autonomous session.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev
Session-start tip: should be `993c6fb` or later (verify with
`git log --oneline -5`).

SESSION TYPE
- Multi-hour autonomous, Don asleep / away.
- ALL-LEVEL DECISION AUTHORITY granted including cross-layer.
- GPU VRAM wide open (RTX 3090 Ti, 24 GB).
- Quality-first posture (HANDOFF §2 doctrine locked).
- Use any skill, tool, or web research for UI/UX decisions before
  committing to a visual design.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. Read in order:
   - HANDOFF_2026-04-25_NEXT_AUTONOMOUS_SESSION.md (this doc)
   - planning/validation_2026-04-24/AUTONOMOUS_RUN_FINAL_REPORT.md
   - planning/validation_2026-04-24/DECISIONS_LOG.md
   - docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md
2. `git log --oneline -10` — confirm tip 993c6fb in history.
3. `git status` — confirm working tree clean.
4. Ollama daemon: confirm running via `curl
   http://127.0.0.1:11434/api/version`. If not, start via
   `"C:/Users/dbhav/AppData/Local/Programs/Ollama/ollama app.exe"`.

================================================================
§EXECUTION PRIORITY
================================================================

Bias toward HIGH-VALUE items first. Suggested order:

1. Phase 1 (~30 min, light-usage):
   ADR-0009 implementation per HANDOFF §4A. Cross-layer focused
   change. Flip status Proposed → Accepted same commit.

2. Phase 2 (~30 min, light-usage):
   `EmbeddingStore::embedded_ids` per HANDOFF §4B. Skip-already-
   embedded path in backfill module. Adds one trait method, one
   impl, one orchestrator branch, tests.

3. Phase 3 (~1 hr, GPU heavy):
   Real-corpus retrieval calibration per HANDOFF §3A. Generate
   500-1000 row synthetic corpus via gemma4:e4b prompts; measure
   recall@k decay; tune ADR-0007 D7 if signal warrants.

4. Phase 4 (~1 hr, GPU heavy):
   Sustained backfill stress test per HANDOFF §3B. Validates the
   pacing-pause defense holds at scale. Updates D7 backfill
   throughput estimates with sustained-real numbers (today's are
   extrapolated).

5. Phase 5 (~1 hr, GPU medium):
   Multi-model coexistence ceiling per HANDOFF §3C. Maps the
   realistic VRAM headroom for ADR-0006 §6 reservations.

6. Phase 6 (variable):
   First-session live UX QA per HANDOFF §3E. Use windows-app-pilot
   + frontend-design-review skills. Document gaps.

7. Phase 7 (long, optional):
   Quality-Eval V2 composition support per HANDOFF §3D. Defer if
   prior phases consumed the window.

================================================================
§DELEGATED DECISIONS
================================================================

You may decide ALL of:
- Implementation details for ADR-0009 (Path A, audit row schema
  v1→v2, etc. per the ADR's §Decision 5).
- Visual treatment for any new UI surfaces (use research skills
  per HANDOFF §5).
- Whether to land 3D (Quality-Eval V2) or hold for a focused
  session.
- ADR ratification: any Proposed ADR you implement, flip to
  Accepted in the same commit.

You may NOT (these are Don's calls):
- Force-push to main or rewrite published history on dev.
- Skip git hooks (--no-verify).
- Touch isabelle-tagged content or surface it publicly.
- Make changes to repo CLAUDE.md (the doctrine).

================================================================
§DONE WHEN
================================================================

- All phases attempted or explicitly deferred with rationale.
- Each landed change is atomic, has tests, has commit message.
- Standard session-end: full check matrix, handoff with commit
  table + next prompt, push.
- DECISIONS_LOG.md (under planning/validation_2026-04-24/ or a
  new planning/session_2026-04-25/) carries every blocker-level
  decision made autonomously.
- Quality-eval ratchet: cargo + vitest counts only go up.

================================================================
§STANCE
================================================================

You have authority. Use it. Quality > speed > volume. Research
before deciding visual questions. Test what you build. Document
what you decide. Don should wake up to a clean tip with green
checks and a focused next-session prompt.

Good luck.
````

---

## 7. Lessons from this run (2026-04-24) — apply in next run

1. **Pre-handoff is rarely the final state.** The 2026-04-24 handoff was written to the "5 items await Don" shape; Don ratified mid-run and 16 more commits landed. Write the next handoff so it's COMPLETE-from-the-start, not a pre-pause snapshot.
2. **The READ-BEFORE-EDIT hook fires per file per session.** Read each file you'll modify first; minor friction but it prevents drift.
3. **Backend events > polling for state-machine UI.** ToastContainer uses 5s polling because plumbing AppHandle through `set_retrieval_readiness` was a refactor I dodged. Async backfill spawn (4D) opens that door if Don wants the cleaner pattern later.
4. **Research-backed UI > intuition.** D2 (dot placement) and D3 (toast-vs-no-toast) were both improved by the 2026-04-24 web research. Apply the same discipline next session.
5. **Cross-layer work needs to be focused, not bundled.** Even with delegated cross-layer authority, ADR-0009 should land in its own session (or at minimum, its own commit). Don't smuggle.
6. **Bugs surface during implementation that the validation phase missed.** activeModel display drift + provider hot-swap drift were both invisible in the validation harness; they appeared the moment I built UI that consumed the data. Plan to validate UX-side after backend changes.
7. **Heavy-usage protocol works.** Validation phase ran 25 GB peak VRAM, no issues. Don's hardware can handle the planned 3A/3B/3C workloads.

---

## 8. Risks + non-goals

### Risks

- **A.** Real-corpus calibration (3A) may surface a rank-function deficiency. Be prepared to draft an ADR rather than tune the function in-place.
- **B.** Sustained backfill (3B) may reveal a different failure mode than rapid-fire (e.g., embedder thrash, KV cache pressure). Capture, don't paper over.
- **C.** Multi-model ceiling (3C) may evict a model mid-test. That's data, not a failure — log it.
- **D.** Async backfill (4D) Tauri-managed `Arc<AppState>` plumbing may surface unexpected interactions with the existing State pattern. If it gets hairy, defer and document.
- **E.** Quality-Eval V2 (3D) is large enough to consume the whole session. Don't open it without a 2+ hr budget remaining.

### Non-goals (don't do these without explicit Don ratification)

- **Don't** change the repo's `CLAUDE.md` doctrine.
- **Don't** revert any commits on `dev` from prior sessions.
- **Don't** force-push or rewrite history.
- **Don't** open `packages/storage` migrations without a focused storage session (DDL changes have their own discipline).
- **Don't** rebrand or rename anything publicly visible (Aether identity is Don's call).
- **Don't** post to LinkedIn or external surfaces (this is Aether engineering, not portfolio work).

---

## 9. Reference paths

- file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-25_NEXT_AUTONOMOUS_SESSION.md (this file)
- file:///C:/Users/dbhav/Projects/aether/planning/validation_2026-04-24/AUTONOMOUS_RUN_FINAL_REPORT.md
- file:///C:/Users/dbhav/Projects/aether/planning/validation_2026-04-24/DECISIONS_LOG.md
- file:///C:/Users/dbhav/Projects/aether/planning/validation_2026-04-24/VALIDATION_REPORT.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0006-hardware-tier-model.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0007-embeddings-onboarding.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0008-tier-detection-from-device-type-and-ram.md
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md
- file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/backfill.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/retrieval.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/tier.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/state.rs
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/RetrievalTab.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/Toast.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/ToastContainer.tsx
- file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/ReadinessIndicator.tsx

---

(end of handoff)
