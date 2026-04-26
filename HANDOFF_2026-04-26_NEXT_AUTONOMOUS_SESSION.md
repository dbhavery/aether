# Handoff — 2026-04-26 → Next Session

**Written:** 2026-04-25 at session close (rewritten complete-from-the-start; supersedes the §9 wave-2 addendum draft).
**Branch:** `dev`. Tip: `17c6b71`. All commits pushed. Working tree clean.
**Authority for next session:** Don's call. Prior run had cross-layer + 12-hour autonomy delegated; the recommendation in §6 is to NOT repeat that posture.
**Quality posture:** Quality-first (unchanged).

---

## 1. State at handoff

### 1.1 Tip
```
git log --oneline -5
17c6b71 chore(evals): re-run 6 scenarios after rewrite — verify Aurora discipline alignment
004339f test(ollama): verify FLASH_ATTENTION=false workaround on Phase 3B failed rows
aacee22 feat(evals): broaden 3 scenario expectations to match Aurora persona discipline (Path A)
fa8ab65 docs(handoff): add Wave 2 §9 — extended autonomy after Don ratification
3ca3df1 fix(trust-drawer): hide disclosure when retrieval block absent
```

### 1.2 Final check matrix
| Check | Result | Δ from session start |
|---|---|---|
| `cargo test --all-features` (apps/desktop/src-tauri) | **293 / 293** | +18 (was 275) |
| `cargo test --workspace` | all green | +14 various |
| `cargo test -p aether-l5-policy --all-features` | 65 / 65 | +8 (security fixes) |
| `tsc --noEmit` (apps/desktop) | clean | unchanged |
| `vitest run` (apps/desktop) | **232 / 232** | +21 (was 211) |
| `python tools/lint-memory-doc/check.py` | OK 122 / 28 | +10 anchors / +3 files |
| `python tools/lint-policy-doc/check.py` | OK 34 / 9 | NEW |
| `python tools/lint-quality-doc/check.py` | OK 60 / 19 | unchanged |

### 1.3 Session aggregate
- **59 commits** since `4614ae7` (start-of-session handoff). 100 files changed: +15,794 / −322.
- **3 ADRs ratified or amended:** ADR-0009 Accepted (audit-row v2), ADR-0006 §6 amended (OLLAMA_MAX_LOADED_MODELS), ADR-0007 D7 amended (sustained-real backfill numbers + F1 contract), ADR-0010 Accepted (Option B cross-encoder; Option A REJECTED with empirical proof).
- **21 D-* decisions** in `planning/session_2026-04-25/DECISIONS_LOG.md`.
- **15 planning deliverables** under `planning/session_2026-04-25/` (reports, research docs, benches, audits).

---

## 2. What shipped (by area)

### 2.1 ADR-0009 cross-layer (Phase 1)
- TurnRequest split into `original_utterance` + `model_input_utterance`
- L5 audit row schema v2: `original_utterance`, `retrieval_provenance`, `schema_version` (implicit v1 deserialize for legacy rows)
- Version-aware AuditList rendering (TrustDrawer v1-badge + v2-expandable)
- ADR ratified Proposed → Accepted
- Code review (PASS-with-notes); all 3 review findings closed

### 2.2 Memory + retrieval
- `EmbeddingStore::embedded_ids` skip-path (Phase 2): backfill no longer brute-force re-embeds
- bge-m3 NaN U+FFFD sanitization: `EmbeddingProvider::embed()` trait-default calls `sanitize_for_embed`; all impls inherit
- ADR-0010 ratified: Option A REJECTED (recall@1 −16.7pp), Option B ACCEPTED (recall@1 +2.8pp via bge-reranker-v2-m3 cross-encoder); production wiring deferred to ADR-0011

### 2.3 Backfill + Ollama
- Async backfill spawn (Phase 4D): `Arc<AppState>`, `start_backfill` returns immediately, `tokio::spawn_blocking` worker, double-start protected, cancel within 200ms
- F1 retry-on-500: 50/100/200ms exponential backoff, `recovered_failures` counter, classifier distinguishes 5xx/transport from 4xx
- F2 UI failure surface: chip strip with red badge for failures, toast branches on failure/recovered counts
- F3 upstream: paste-ready Ollama bug report at `OLLAMA_UPSTREAM_BUG_REPORT.md` with prior art at ollama#13572
- **FLASH_ATTENTION=false workaround CONFIRMED** (65/65 on previously-failing rows)

### 2.4 HuggingFace embedder (Phase 4C)
- Path X: persistent Python helper at `tools/hf_embed_helper/embed.py`
- `HfEmbeddingProvider` in `packages/l2-memory/src/hf_provider.rs`
- `swap_embedding_provider_for_config` extended for `hf:` prefix
- `bge-small-en-v1.5` actually loadable as Spark default per ADR-0007 D7

### 2.5 Quality-Eval V2 + Aurora discipline
- Composition (Phase 7): persona/memory/vision/voice composers in `tools/evals/composition.py`
- Eval scenario broadening applied (Path A): 3 scenarios rewritten to match Aurora's persona discipline
- Re-run: 2/6 PASS → 3/6 PASS. `voice_transcription` flipped via referential paraphrase match
- New expectation kind `requires_any` added to `tools/evals/expectations.py`
- Honest holdouts: `vision_response_quality` (needs fridge fixture), `memory_appropriateness` (Aurora 10th paraphrase variant unanticipated)

### 2.6 Security + audit hardening
- HIGH-1: `audit_seal::canonical_bytes` branches on schema_version → preserves v1 hash chain across the v2 wire bump
- MEDIUM-1: `format!("{:?}", h.domain)` replaced with `h.domain.label()` (stable wire string)
- MEDIUM-2: `RetrievalProvenance::hits` capped at 16 (writer + defensive in `engine.rs::write_audit`)
- 4 new round-trip + tamper tests in `audit_seal.rs`

### 2.7 UX + chrome (Phase 6 + fixes)
- Live UX QA: 8 screenshots, NEEDS-POLISH verdict, 3 findings
- Header responsive at 1024px: ProviderBadge truncates with title fallback, persona-select + About hidden under breakpoint
- Trust drawer focus trap: `aria-modal="true"`, capture-phase keystroke swallow, focus restore on close, Escape closes
- AuditList chevron hidden when `block_present:false` (no more empty disclosures)

### 2.8 Documentation + research
- 7-layer architecture diagram (`docs/ARCHITECTURE_DIAGRAM.md`, 4 Mermaid diagrams)
- HF embedder enablement guide (`docs/HF_EMBEDDER.md`)
- Audit-row UI research (Linear / Stripe / Carbon synthesis)
- Test coverage gap audit (49/52 Tauri commands lack name-level tests; 14/28 components without test files)
- Doc-anchor drift fix (D-005 closed an OPEN_QUESTIONS item)
- ADR-0009 reference sweep across docs/MEMORY-V2-ARCHITECTURE.md, ADR-0005, HANDOFF_2026-04-24

---

## 3. Open items awaiting Don

### 3.1 Manual / 5-minute items (do tonight)
1. **`OLLAMA_FLASH_ATTENTION=false` in startup env** — workaround empirically confirmed; set permanently. Without this, F1 retry helps but doesn't eliminate the content-deterministic NaN failures.
2. **Commit `tools/evals/fixtures/fridge_open.jpg`** — vision_response_quality scenario blocked on real fixture.
3. **Comment on ollama#13572** — paste-ready text in `OLLAMA_UPSTREAM_BUG_REPORT.md` §"Workaround verification 2026-04-25". Optional outreach.

### 3.2 Decision items (this week)
4. **Memory_appropriateness 10th paraphrase variant** — Aurora produced "Got it. Let's leave that out of it." outside the 9 documented patterns. Either (a) add the 10th pattern to `tools/evals/__main__.py` (~2 min), or (b) leave as canary for persona evolution (recommended — honest signal beats gamed pass).
5. **Aurora-strict canary suite** — defensive infra: parallel literal-token test suite that runs but doesn't gate. Detects persona drift. ~1-2 hr in `tools/evals/`.

### 3.3 Future-session items
6. **ADR-0011 cross-encoder production wire** — deferred per data-driven recommendation. Modest +2.8pp lift; per-query rerank latency cost not free. Wait until Aether has real conversation data to measure against — synthetic-corpus rank evolution may not predict real-world impact. Scope ADR-0011 around *which* retrieval calls get the rerank pass (audit-search? everyday turns?), not whether to enable globally.
7. **Code review #2 e2e test** — landed but mirrors `submit_turn` internals (real entry point requires AppHandle hostile to unit tests). When Tauri test scaffolding matures, replace with a true integration test.

---

## 4. Surprise findings (worth re-reading)

1. **Audit row v1 had no utterance field at all** (D-001). ADR-0009's "augmented utterance pollution" framing was wrong — v2 is strictly additive.
2. **OLLAMA_MAX_LOADED_MODELS=3 is the binding ceiling, not VRAM** (D-006). 7 GB stranded on Forge under stock config.
3. **Phase 3B's "1.3% Ollama 500" is content-deterministic NaN**, not load (D-019, F3 report). Workaround: `OLLAMA_FLASH_ATTENTION=false` (verified 65/65).
4. **Option A (recency-weighted combine) actively HURT recall** (D-018). Reflex fix was wrong fix. Cosine + strict-tiebreak preserved as baseline.
5. **Header overflowed at 976px** — first-impression breaker nobody had noticed (D-?, fix `deb0c3a`).
6. **Aurora's persona discipline is broader than the eval coverage** — 10th paraphrase variant outside the documented 9.

---

## 5. Process incidents

Five working-tree contamination incidents from parallel-agent index races (D-008, D-011, D-012):
- Doc-gap agent's `git add <list>` swept up D-005 work
- Phase 7 reported 3 stomps during its run
- Phase 4C bundled audit_seal test agent's changes
- Phase 3A bundled HF-embedder doc files
- Security fix's first MEDIUM-2 attempt swept Phase 7's untracked planning files (reverted via `75a3eec`)

**Mitigation for next session (REQUIRED if dispatching parallel agents):**
- Use `git commit -o <pathspec>` not `git add . && git commit`
- OR worktree-per-agent via `superpowers:using-git-worktrees`
- OR serialize `planning/` writes through one agent at a time

---

## 6. Recommendations for the next session

1. **Don't dispatch another 12-hour autonomous run on the same surface.** Diminishing returns near the end of this one. Either Don-driven half-hour to apply manual items, or pivot to user-facing milestone work.
2. **Before any more retrieval work, measure on a real transcript.** Pull 200-500 turns from real `memory.json`, run the recall harness. If recall@5 holds at >90%, ADR-0011 is genuinely defer-able. If it craters, synthetic corpus misled and ADR-0011 is urgent.
3. **Adopt worktree-per-agent.** The 4-5 documented index races cost real audit-trail clarity. Repo CLAUDE.md should reference worktree skill for autonomous sessions.
4. **Treat honest-FAIL eval results as features.** The 10th paraphrase variant, Option A's REJECTED outcome, missing fridge fixture surfacing as FAIL — signals about Aurora's discipline + test coverage gaps. Don't pattern-hunt to bury them.
5. **Sleep on ADR-0011.** Cross-encoder per-query latency may not be worth +2.8pp recall@1 for everyday turns; might be worth it for audit-search use case. Scope around *which* calls get rerank, not global enable.

---

## 7. Paste-verbatim next-session prompt

````md
You are Claude Code, opening Aether for the next session after the
2026-04-25 autonomous run.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev
Session-start tip: should be `17c6b71` or later.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. Read in order:
   - HANDOFF_2026-04-26_NEXT_AUTONOMOUS_SESSION.md (this doc)
   - planning/session_2026-04-25/DECISIONS_LOG.md (D-001 through D-020)
   - docs/adr/ADR-0010-rank-function-recency-weighted-combine.md
     (Option B Accepted, production wiring deferred to ADR-0011)
   - planning/session_2026-04-25/RETRIEVAL_CALIBRATION_REPORT.md
   - planning/session_2026-04-25/QUALITY_EVAL_V2_POST_REWRITE_REPORT.md

2. `git log --oneline -10` — confirm tip 17c6b71 in history.

3. `git status` — confirm working tree clean.

4. Ollama daemon: confirm running. If Don has not yet set
   `OLLAMA_FLASH_ATTENTION=false` permanently, surface that as the
   highest-leverage 5-minute action.

================================================================
§POSTURE
================================================================

Default: NOT autonomous. Don-driven half-hour or pivot to milestone
work (avatar/voice). If Don explicitly opens autonomy, adopt the
mitigation in §5 of this handoff: worktree-per-agent OR `git commit -o`
discipline OR serialize planning writes.

================================================================
§DECISIONS AWAITING DON (per §3 of this handoff)
================================================================

Manual: FLASH_ATTENTION env, fridge fixture, ollama#13572 comment.
Decisions: 10th-paraphrase-variant, Aurora-strict canary suite.
Future: ADR-0011 cross-encoder production wire (defer recommended).

================================================================
§DELEGATED DECISIONS (still applies if Don re-opens autonomy)
================================================================

You may decide:
- Implementation details for ratified ADRs
- Visual treatment for new UI surfaces (use research skills)
- ADR ratification: any Proposed ADR you implement, flip to Accepted
  in the same commit

You may NOT (Don's calls):
- Force-push, rewrite published history on dev
- Skip git hooks (--no-verify)
- Touch isabelle-tagged content
- Modify repo CLAUDE.md
- Open packages/storage migrations
````

---

## 8. Reference paths (everything that exists)

### ADRs touched this session
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0006-hardware-tier-model.md (§6 amended)
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0007-embeddings-onboarding.md (D7 amended)
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md (Accepted)
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0010-rank-function-recency-weighted-combine.md (Accepted, Option B)

### Session deliverables (planning/session_2026-04-25/)
- DECISIONS_LOG.md (D-001 → D-020)
- RETRIEVAL_CALIBRATION_REPORT.md (Phase 3A)
- BACKFILL_STRESS_REPORT.md (Phase 3B)
- MULTI_MODEL_CEILING_REPORT.md (Phase 3C)
- QUALITY_EVAL_V2_REPORT.md + QUALITY_EVAL_V2_POST_REWRITE_REPORT.md (Phase 7)
- ADR_0009_CODE_REVIEW.md
- SECURITY_REVIEW.md
- AUDIT_ROW_UI_RESEARCH.md
- TEST_COVERAGE_AUDIT.md
- UX_AUDIT.md (Phase 6) + ux_audit_screenshots/ (8 PNGs)
- EVAL_SCENARIO_BROADENING.md (the rewrite plan, applied)
- OLLAMA_UPSTREAM_BUG_REPORT.md (paste-ready for ollama#13572)
- 13 bench/data files (synthetic_corpus, recall_at_scale_*, backfill_stress_results, multi_model_ceiling, flash_attention_workaround_results, quality_eval_v2_*)

### New source surfaces
- file:///C:/Users/dbhav/Projects/aether/tools/hf_embed_helper/embed.py (HF helper)
- file:///C:/Users/dbhav/Projects/aether/tools/lint-policy-doc/check.py (new rot-guard)
- file:///C:/Users/dbhav/Projects/aether/tools/evals/composition.py + test_composition.py + expectations.py
- file:///C:/Users/dbhav/Projects/aether/packages/l2-memory/src/hf_provider.rs (new)
- file:///C:/Users/dbhav/Projects/aether/docs/HF_EMBEDDER.md (new)
- file:///C:/Users/dbhav/Projects/aether/docs/ARCHITECTURE_DIAGRAM.md (new)

---

## 9. Lessons (apply in next run)

1. **Complete-from-the-start handoffs** — this one is rewritten end-to-end at session close, not a pre-pause snapshot.
2. **Concurrency hygiene is the dominant failure mode of parallel-agent dispatch.** Five documented stomps; mitigation in §5.
3. **Honest failures > false passes.** Option A REJECTED, 10th paraphrase variant surfaced, fridge fixture absence surfaced as FAIL — all are signals worth keeping.
4. **Empirical ratification beats reflexive ratification.** ADR-0010 spent the time to measure both options before flipping; the data overruled the obvious answer.
5. **Atomic small commits.** 59 commits, 1 reverted (the cap-hits race), zero regrets.
6. **Read-before-edit hook is annoying but right.** Cooperate.
7. **Don't dispatch >5 parallel agents on the same working tree.** Race incidents scale faster than agent count.

---

(end of handoff)
