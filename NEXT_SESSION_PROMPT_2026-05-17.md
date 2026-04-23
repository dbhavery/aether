# Next-session prompt — 2026-05-17

> **Paste the fenced block below into the next Claude Code session, verbatim.**
>
> This prompt was authored at session end on 2026-05-17 with Don's full
> grounding captured inline. It replaces the stale "current status" block
> that has been causing repeated drift across sessions (Decision #32
> fires). The compact doctrine grounding below saves ~15-20 min of
> re-reading for the next agent.
>
> If this file exists and is <7 days old, prefer it over any prompt
> Don pastes that restates subsystem status — the repo is the source of
> truth, not the prompt template.

---

````md
You are Claude Code, continuing work on Aether overnight.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

SESSION TYPE
- High-autonomy all-nighter. Don has delegated tactical decisions to you within the bounds defined below. He is asleep; do not block waiting for him on anything except the items in §RESERVED DECISIONS.
- Scope ambition: close three high-leverage Wave-1-adjacent items, then push into Tier 2 if time remains. Do NOT attempt Tier 3 without explicit pre-authorization.

================================================================
§STATUS CORRECTION (read first, supersedes any conflicting prompt)
================================================================

The earlier prompt template Don uses still lists Presence V1 step 4, Memory V2 step 3, Quality-Eval live-capture, and NFR skeleton as "pending." All four shipped on 2026-05-17 in the prior session tree. Do NOT redo them. Per Decision #32, repo beats prompt.

Verified tip at session start (confirm with `git log --oneline -10`):
- `fa1c287` — docs: session-end handoff for ultra-long next session
- `cabaf4a` — feat(tools/evals): v1.2 — structured capture + replay
- `a4a571e` — chore: switch default local model from llama3 / llama3.2 to gemma4
- `86798ee` — docs: add NFR skeleton — closes audit gap #2
- `37f00fa` — feat(presence): rot guard + flip presence doc to current — Presence V1 step 4
- `a02a851` — feat(apps/desktop/src/lib): memory telemetry kinds + TS parity test — Memory V2 step 3 slice 3
- `b43a9b0` — feat(apps/desktop): memory_service with per-domain gate + audit + telemetry — Memory V2 step 3 slice 2
- `939d953` — feat(l5-policy): register Memory V2 coarse caps in wave3_default — Memory V2 step 3 slice 1

Working tree should be clean. 28+ commits ahead of `origin/dev`. **Do not push.**

Actual subsystem state (trust this, not the template):
- Vision V1 — closed, rot-guarded (Current as of 2026-05-07, 51 anchors).
- Voice V1 — closed, rot-guarded (Current as of 2026-05-13, 48 anchors).
- **Presence V1 — closed**, rot-guarded (Current as of 2026-05-17, 39 anchors). Two-axis (assistant posture + user attention); session lifecycle labeled Future/V2.
- **Memory V2 — through step 3.** L5 preset wired, shell `memory_service.rs` gates per-domain Auto/Ask/Deny, telemetry + audit emission, sampled read audit, TS parity. Step 4 (Trust drawer Memory tab) is next. Step 5 (retention sweep) is gated by an unresolved enum decision (see §RESERVED).
- **Quality-Eval V1 — v1.2.** Live Ollama capture + structured JSON + `--replay-from` + 13-test unit suite. Session-log replay importer is next.
- Glossary (gap #1): shipped. NFR skeleton (gap #2): shipped. Gaps #3-6 pending.
- Default local model: `gemma4` (flipped 2026-05-17). Concerns unverified on Aether workload — FA hang on 31B dense, slow throughput on 26B MoE per Morning Intel memory. If real inference fails, the fix is flipping two constants back (see `HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md` §4 Risk A).

================================================================
§DOCTRINE GROUNDING (compact — the full doctrine is 28 days old but the hard rules remain in force)
================================================================

Read if needed: `planning/00_VISION_AND_GUARDRAILS.md`, `planning/01_product_doctrine.md`, `planning/02_product_family.md`. Don flagged UI/front-end/production implementation has drifted from these, but the architectural and product-shape rules below are still authoritative.

**The bar** — "indistinguishable from a real human companion." Operationalized as six quality domains × one meta-criterion:
- chat realism, tool-use judgment, vision response quality, voice transcription, memory appropriateness, presence-aware behavior.
- Meta: **calibrated confidence**. Overconfident wrongness is worse than correct hedging.

**Product family** — three tiers, share identity/onboarding/trust patterns but not shortcut stacks:
- **Aether OSS Preview** — open-source wedge; free; may borrow MuseTalk/TalkingHead/Wav2Lip/Whisper/Parakeet/Distil-Whisper/open TTS/Tauri aggressively for speed.
- **Aether Pro** — commercial flagship; "we write our own from here on." Custom-built must-own layers. Mobile continuity, richer avatar, full voice + avatar modes, tool use, trust center, red-team ready.
- **Isabelle / Isabelle_Kunstig** — Don's privileged profile on top of Pro. Never a separate codebase; additive only.

**Seven must-own layers (non-absorbable; L5 doesn't route, L1 doesn't do presence, L2 isn't "the DB"):**
1. L1 interaction timing — turn FSM + timing contracts (250/800/2000/4000ms) + reflex router (embedded classifier).
2. L2 memory kernel — multimodal ingestion, scoped recall, editable memories, provenance, decay, user-enforced forgetting.
3. L3 presence controller — internal state → visible social behavior (gaze, blink, micro-motion, anti-uncanny).
4. L4 model router — latency-aware local-vs-remote; factors privacy/cost/task/memory-confidence/tool availability.
5. L5 policy engine — **core of trust moat.** Capability permissions, scoped resources, approval workflow, audit logs.
6. L6 persona compiler — onboarding → prompts + phrase pools + animation + voice + memory-salience.
7. L7 onboarding/trust UX — **cannot be outsourced.** User-visible surface that establishes trust.

**Hard rules (doctrine-level, don't violate without explicit sign-off):**
- No "close-enough SaaS" in user-relationship or moat layers.
- UX outranks implementation convenience.
- UI stack: HTML/CSS/JS. Tauri family desktop long-term. pywebview OSS-Preview-only tactical.
- Rust for engines/infra; TS for UI/bindings/light orchestration only.
- Monorepo with shared infra (`event-bus`, `storage`, `telemetry`, `types`, `ui-kit`) as the only cross-cutting layer.
- Local-first by default. Remote calls deliberate + visible + policy-governed.
- L5 is single writer for side effects. No direct executor calls outside l5-policy.
- Rot guards ≠ acceptance criteria. Tests/evals enforce behavior; rot guards enforce doc↔code anchor presence.
- Observation-vs-action distinction is load-bearing. Presence emits telemetry only (never L5 audit). Memory writes and tool calls emit audit.
- No raw-media persistence. Image/audio bytes transient at every layer. Transcript text is persistable because it becomes a turn.
- No silent fallback (Voice V1 contract, generalized: transport/parse/provider errors surface visibly).
- One `packages/l*-*/` layer per session. Shell-layer work is free; it doesn't count against the limit.
- No cross-layer imports between `packages/l*` siblings. Coordinate via `event-bus` or L5/L6 typed outputs.
- Private assets (Isabelle-tagged) never enter public distributables. `tools/lint-private-asset-leak/` is the build-time gate.
- Legacy Python tree (`src/`, `desktop/`, `frontend/`) is coexistence-only. Don't "clean up" opportunistically. CLAUDE.md §7.

**Architectural invariants shaping tactical choices:**
- Memory V2 shell-gate pattern mirrors Media/Mic: shell tri-state is the user gate, L5 records audit. Don't try to move the gate into L5 proper; doctrine doesn't require it, and it breaks the "L5 doesn't own UX" rule.
- Vision/Voice/Presence/Memory arch docs are section-for-section mirrors. Deliberately so that one mental model covers all modalities. Preserve when extending.

================================================================
§RESERVED DECISIONS (require Don's sign-off; do NOT resolve autonomously)
================================================================

1. **L2 kernel vs shell `MemoryDomain` enum mismatch.** L2 kernel has Personal/Work/Health/Finance/Creative/System. Shell `memory_config` has Session/Durable/Facts/Projects/Preferences/Artifacts. Three options in `HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md` §4 Risk C. This blocks Memory V2 step 5 (retention sweep). If you find yourself needing this, STOP and write the handoff — do not pick an option.

2. **Open glossary decisions from `docs/GLOSSARY.md` §11.** AC house style, requirement ID scheme, presence axis namespace (sub-layer partition), Cross-system spec doc shape. These are Don's calls, not yours.

3. **Any doctrine-level change.** Seven-layer structure. Product-tier boundaries. "No close-enough SaaS" rule scope. UI stack choices.

4. **`git push`.** Never, regardless of how clean the tree is.

5. **Avatar / viseme / photoreal L3 social-behavior rendering.** Doctrine targets it for Pro; no shipped code today. If you find yourself scoping it, STOP.

6. **Onboarding wizard redesign.** L7 onboarding is must-own. `planning/06_onboarding_spec.md` has the 7-step wizard spec. Don't unilaterally change shape.

7. **Any new `packages/*/` or `apps/*/` directory.** CLAUDE.md §3: coordinator-gated. If you need one, STOP and record the proposal in a planning note — do not scaffold.

8. **Removing or weakening rot guards, tests, lint, or layer-boundary enforcement.** Absolutely off limits.

9. **Gemma-4-specific rollback.** If Gemma 4 shows real-world problems (hang, garbage output, etc.) during capture runs, document it in the handoff and leave the flip in place. Don decides whether to roll back.

================================================================
§DELEGATED DECISIONS (you may decide; use best judgment)
================================================================

Within the scope of the Tier 1 / Tier 2 items below:
- Trait shapes, method signatures, module organization.
- Test patterns and test-data choices.
- Telemetry kinds (additive) and their TS mirrors.
- Commit messages (follow the `<scope>: <subject>` + co-author pattern already established).
- Execution report and handoff content.
- Which optional sub-tasks inside a tier to drop if time is short.
- Small helper scripts that support the work.
- Refactoring within a single file for readability (not structural).

================================================================
§TIER 1 — MUST DO (budget ~3-4 hours each, order-sensitive)
================================================================

### Tier 1A — Memory V2 step 4 (Trust drawer Memory tab)

**Scope:** First UI surface consuming the `memory_service` API from step 3 slice 2. The user-visible Memory V2 experience.

**Blocker from the previous aborted attempt:** the other agent paused on "step 4 requires per-item forget and edit, but `SessionMemoryStore` only has append/recent/clear_session." Don has pre-authorized **Option B with strict scope**: extend the L2 `SessionMemoryStore` trait with two additive methods:

```rust
fn remove(&self, session_id: &str, sequence: u64) -> Result<bool, L2Error>;
fn update(&self, session_id: &str, sequence: u64, new_content: String) -> Result<bool, L2Error>;
```

Both return `Ok(false)` if the row doesn't exist (silent no-op is correct; the caller can check). SQLite pk is already `(session_id, sequence)` — migration is a no-op.

**Scope guardrails (these are hard boundaries; violating creates step-5 entanglement):**
- ONLY these two new trait methods. Not `list_by_domain`, not `tombstone`, not `content_hash`, not retention fields.
- NO changes to `TurnMemoryRecord` shape (no new domain field, no new metadata, no new sequence type).
- NO changes to `clear_session` semantics.
- NO migration logic.
- NO touching the `MemoryKernel` trait or `MemoryItem` struct. That trait has zero consumers today; leave it alone.

**Implementation plan:**
1. L2 trait extension (`packages/l2-memory/src/session.rs`) — 2 methods, add to trait, add to `InMemorySessionMemoryStore` impl + unit tests.
2. L2 SQLite impl (`packages/l2-memory/src/sqlite_session.rs`) — 2 methods + unit tests.
3. Shell `memory_service.rs` `memory_edit` — grow a `new_content: String` parameter (the doc comment literally promised this), flow through to `store.update()`.
4. Shell `memory_service.rs` new: `memory_forget_item(domain, session_id, sequence) -> MemoryForgetOutcome` — flows through to `store.remove()`. Same gate/audit/telemetry pattern as existing `memory_forget`.
5. New Tauri commands (`apps/desktop/src-tauri/src/commands.rs`):
   - `memory_list(domain: MemoryDomain, session_id: &str) -> MemoryListPayload` — returns the items (today: session turns for Session domain; empty for the other five with honest `empty_reason: "no backing store yet"`).
   - `memory_forget(domain, session_id)` — wraps existing `AppState::memory_forget`.
   - `memory_forget_item(domain, session_id, memory_id)` — wraps the new shell method. Parse `memory_id` → sequence using the existing `mem-{session_id}-{seq}` convention.
   - `memory_edit(domain, memory_id, new_content)` — wraps the grown method.
6. TS types in `apps/desktop/src/lib/api.ts` for the four new commands.
7. `apps/desktop/src/components/MemoryTab.tsx` (new) — six per-domain lanes, row rendering, forget/edit buttons, forget-all-in-domain action. For the five empty lanes (Durable/Facts/Projects/Preferences/Artifacts today), render an honest "Storage for this domain arrives with Memory V2 step 5" empty state instead of faking content.
8. Mount MemoryTab inside `TrustDrawer.tsx` as a sibling to History and Audit tabs.
9. Approval-modal wiring: reuse the existing media/mic `ApprovalPayload` pattern for Facts/Artifacts forget-item and edit operations. Post-modal entry points are `memory_write_after_approval` (already exists), and for forget/edit, add `memory_forget_item_after_approval` / `memory_edit_after_approval` mirror methods in `memory_service.rs`.
10. Tests: Rust unit (commands + new trait methods + shell methods), Vitest component (MemoryTab per-lane rendering + forget/edit flows).

**Check matrix after Tier 1A:** cargo fmt, cargo check --workspace, cargo test --workspace, cargo test -p aether-l3-presence, cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp -- --test-threads=1, shell tests with all features, all three doc rot guards, evals dry-run, evals adversarial, `tools/evals/test_capture_replay.py`, pnpm typecheck, pnpm build, pnpm test.

**Commit cadence:** 3-4 scoped slices. Suggested: (1) L2 trait extension, (2) shell service grow, (3) Tauri commands + TS, (4) MemoryTab component + tests.

### Tier 1B — Flake cleanup (~30 min, high compound leverage)

Two known env-seam flakes:
- `packages/l6-persona/src/.../yaml_persona_pack_merges_into_catalog` — `AETHER_PERSONAS_DIR` contamination under parallel tests.
- `packages/l4-router/src/providers/ollama.rs::from_env_uses_defaults_when_vars_unset` — `AETHER_OLLAMA_*` contamination.

Both pass in isolation and under `--test-threads=1`. Migrate the test seams to per-test `TempDir` + scoped env guard pattern (see `EnvGuard` usage in `ollama.rs` tests for the pattern). Do NOT weaken the assertions. One commit: `test: kill env-seam flakes via TempDir + scoped EnvGuard`.

### Tier 1C — `scripts/current_status.sh` (~10-15 min)

Mitigation for the stale-prompt pattern that's cost hours of friction across the last three sessions. Implementation: tiny script that reads the latest `HANDOFF_*.md` in the repo root and prints the track-status-snapshot section. Plus a matching Python fallback for Windows users who prefer it.

Usage:
```
./scripts/current_status.sh
# outputs the §3 subsystem status + §2 check matrix + ahead-of-origin count
```

Don's request: future prompts should start by running this and pasting the output, instead of restating stale status. Include a one-line instruction at the top of the generated handoffs: "To get current status, run `./scripts/current_status.sh` — do not restate from memory."

Commit: `chore(scripts): add current_status.sh — kills stale-prompt pattern`.

================================================================
§TIER 2 — IF TIME AFTER TIER 1 (order-sensitive)
================================================================

### Tier 2A — Quality-Eval session-log replay importer

Small Python script that reads an Aether telemetry log (exported from the shell via a future "export telemetry" Tauri command — or, for now, read the in-memory `telemetry` ring via a new dev-only `telemetry_export` command) and emits capture JSONs matching the v1.2 schema from this morning's `cabaf4a`. This lets `--replay-from` cover real conversations, not just manually seeded scenarios.

Scope:
- `tools/evals/session_log_import.py` — CLI that takes a telemetry JSON export and a scenarios-root, emits one capture per matching scenario.
- Matching heuristic: match on `persona_id` + first user-turn content. If the scenario's prompt appears in the telemetry, emit the capture.
- Tests in the existing `tools/evals/test_capture_replay.py` style.

Commit: `feat(tools/evals): v1.3 — session-log import for replay`.

### Tier 2B — `tools/lint-quality-doc/` + flip QE doc to current

Mirror exactly the pattern of `tools/lint-presence-doc/check.py` (shipped in `37f00fa`). Anchor manifest covering the QE doc's claimed files/symbols/strings. Flip `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` from "Design-only as of 2026-05-14" to "Current as of 2026-05-18" and reconcile any drift (v1.1 + v1.2 work shipped since the doc was written).

Commit: `feat(quality-eval): rot guard + flip doc to current`.

### Tier 2C — Autonomy preset picker UI

Backend is ready: `AppState::apply_preset(Option<AutonomyPreset>)` in `state.rs` rebuilds the engine atomically. No UI today (README explicitly lists "No autonomy preset picker" as v0 scope).

Scope:
- New Settings section "Autonomy" with three radio options (Observer / Assistant / Operator) + a "Not chosen (baseline)" option.
- Tauri commands: `current_autonomy_preset` (exists) + `set_autonomy_preset(preset: Option<String>)`.
- On change: apply + toast "Autonomy set to Operator" + write to a new `autonomy.json` policy file (same additive-default-safe pattern as the other configs).
- Tests.

Commit: `feat(apps/desktop): autonomy preset picker in Settings`.

### Tier 2D — Persona picker UI

Similar shape: backend has `AppState::catalog` and `switch_persona`; only "Aurora" surfaces today. Add a persona dropdown in the header, wire `switch_persona` command. If multiple personas ship (check `catalog` at runtime), show them; if only one, show the current persona name without a dropdown.

Commit: `feat(apps/desktop): persona picker header`.

================================================================
§TIER 3 — FORBIDDEN WITHOUT EXPLICIT SIGN-OFF
================================================================

- Memory V2 step 5 (retention sweep) — forces the L2/shell enum reconciliation (RESERVED #1).
- Memory V2 step 6 (embeddings).
- Memory V2 step 7 (rot guard — do after steps 4 and 5).
- Onboarding wizard redesign (RESERVED #6).
- Avatar / viseme / L3 social-behavior rendering (RESERVED #5).
- Pro-tier sync / Isabelle sync design work.
- L5 SQLite persistence (Wave 3.5).
- L5 audit hash-chain + HMAC (Wave 4).
- Cost-cap evaluator Stage 0 (Wave 4).
- Privacy-posture gate on remote routes (Wave 4).
- Forward-looking requirement IDs (RESERVED #2 — glossary §11).
- `docs/AC-STYLE.md` (RESERVED #2 — glossary §11).
- OSS/Pro assembled spec views (doctrine docs are stale; Don wants to refresh doctrine first).
- Light RTM view (downstream of requirement IDs).
- Doctrine doc refresh (Don explicitly reserved; 28 days stale, he'll do the refresh pass himself).
- `git push`.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `git status` and `git log --oneline -10`. Verify the commit list in §STATUS CORRECTION.
2. Read `HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md` end to end — especially §4 (Risks) and §5 (on-deck).
3. Read `HANDOFF_2026-05-17_MEMORY_STEP3_PRESENCE_STEP4_NFR.md` for the earlier consolidated handoff context.
4. If repo state disagrees with §STATUS CORRECTION, update status and stop — do not guess which is right. Don's left a single `scripts/current_status.sh` mitigation target for exactly this case; if you shipped Tier 1C and the next session still hits this, the script is failing its purpose.

================================================================
§SESSION-END DISCIPLINE (mandatory)
================================================================

Before stopping:

1. Full check matrix (see Tier 1A for the list). All green.
2. Working tree clean.
3. Execution reports for each tier you finished — follow the pattern of `MEMORY_V2_STEP2_EXECUTION_REPORT_2026-05-16.md` etc.
4. One consolidated session handoff (`HANDOFF_2026-05-18_<shortname>.md`) covering:
   - what shipped this session (commit table),
   - full check matrix results,
   - subsystem status after this session,
   - risks / alerts for the next run,
   - decisions log (new additions only, continuing from #45 in today's handoff),
   - backlog re-prioritization if warranted,
   - next recommended prompt (paste-verbatim).
5. Update this session's own auto-memory if applicable (see `C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/` — today's session added `project_aether_gemma4_adoption.md`, `project_aether_state_2026-05-17.md`, and `feedback_stale_prompt_drift.md`; similar lightweight additions as needed).

================================================================
§RETURN FORMAT
================================================================

When you stop, respond in this structure:

## Tier completion
- Tier 1A Memory V2 step 4: done / partial / blocked (reason)
- Tier 1B flake cleanup: done / skipped (reason)
- Tier 1C current_status.sh: done / skipped (reason)
- Tier 2 entered: yes (which) / no

## Commits
- SHA — message

## Full check matrix
- (list; all should be green)

## Subsystem status post-session
- Vision V1: unchanged, closed
- Voice V1: unchanged, closed
- Presence V1: unchanged, closed
- Memory V2: previous → now
- Quality-Eval V1: previous → now

## Risks / alerts for next session
- (new risks surfaced this run; which existing risks from today's §4 are retired)

## Decisions log (new this session)
- #46 onward

## Anti-drift corrections
- (any stale prompts or memory notes you had to correct)

## Next recommended prompt
(paste-verbatim, following the shape of this prompt)

================================================================
§STANCE
================================================================

Don has handed tactical decisions to you. Use that trust conservatively: pick well within the delegated scope; stop cleanly at the boundary of RESERVED decisions; leave crisp artifacts for him to review in the morning; do not invent work the scope doesn't name.

If you hit a genuine blocker you cannot resolve within the delegated scope, WRITE THE HANDOFF AT THAT POINT. A short handoff capturing a blocker is worth more than an aggressive push that produces a tangle. "Partial scaffold with a clear TODO beats fake completeness" (CLAUDE.md §9).

Ship Tier 1 cleanly. Earn Tier 2. Do not start Tier 3.

Good night.
````
