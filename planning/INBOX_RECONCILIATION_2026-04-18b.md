---
status: working
date: 2026-04-18
owner: Don (coordinator) + Agent C (roadmap reconciliation support)
---

# Inbox Reconciliation — 2026-04-18b

Every file in `file:///C:/Users/dbhav/Projects/aether-planning/inbox_2026-04-18b/` is classified here with an explicit disposition. No silent drops.

Dispositions:
- **adopt as canonical** — replace the canonical file with the inbox version.
- **merge into canonical** — pull specific content from inbox into canonical, then retire the inbox file.
- **keep as reference only** — preserve for citations/audit; canonical is authoritative.
- **retire** — move to `archive/` once confirmed absorbed.

---

## 1. `aether_sources_matrix.md` vs canonical `sources_matrix.md`

**Inbox:** 155 lines. Grouped sources table with explicit "Why used" column + `[cite:NN]` markers. Columns: ID, Type, Topic, Why used, Docs (OSS / PRO / XSYS).

**Canonical:** 170 lines. Grouped sources table without "Why used" column and without cite markers. Columns: ID, Type, Topic, Applies to (doc numbers).

**Differences:**
- Inbox has explicit rationale per source ("Why used") that canonical drops.
- Inbox uses doc tags (OSS / PRO / XSYS); canonical uses numbered-spec references (05, 06, etc.).
- Canonical is slightly richer in entry count and aligned with the numbered-spec file structure.
- Inbox carries `[cite:NN]` markers which are not used elsewhere in the planning folder.

**Contradictions:** none substantive. Both are surveys of the same underlying research output.

**Disposition:** **merge into canonical.** Pull the "Why used" column from the inbox version into `sources_matrix.md` as an additional column per row (sources don't change; rationale adds auditability). Retain canonical's doc-number references; drop inbox's `[cite:NN]` markers as non-canonical. After merge, retire the inbox file to `archive/`.

**Coordination:** no agent currently owns this; coordinator performs merge in the next pass.

---

## 2. `aether_cross_systems_spec.md`

**Inbox:** 123 lines. Product-family-doctrine + shared architecture principles + shared recommended stack + cross-system standards for onboarding / permissions / trust / performance / updates / Isabelle inheritance / success profile. Heavy `[cite:NN]` marker usage.

**Canonical equivalent:** content was **absorbed across `04`–`16`** during the initial planning pass (per `COMPARISON_REPORT.md` and `HANDOFF_2026-04-18.md`). Specifically:
- UX / onboarding standard → `04_user_modes.md`, `05_ux_principles.md`, `06_onboarding_spec.md`.
- Permissions / autonomy standard → `12_permissions_autonomy.md`.
- Trust / red-team standard → `13_trust_security_redteam.md`.
- Performance tier standard → `14_performance_tiers_vram.md`.
- Update/release standard → `15_updates_releases.md`.
- Shared stack → `16_tech_stack.md`.
- Isabelle inheritance → `roadmaps/isabelle_private.md`, `02_product_family.md`.

**Differences:**
- Inbox is a single consolidated doc; canonical splits into numbered specs (progressive-disclosure pattern).
- Inbox does **not** yet reflect the 7 locked decisions from this session (Tauri doctrine, monorepo, layer-count, etc.).
- Inbox's family-doctrine section is softer than `01_product_doctrine.md` (does not explicitly state "Aether Pro onward is primarily custom-written").

**Contradictions:** inbox doctrine language is weaker than canonical `01_product_doctrine.md`. Treating inbox as canonical would re-open the no-close-enough-SaaS lock. **Do not adopt inbox doctrine language.**

**Disposition:** **keep as reference only.** The inbox file is research provenance for citations; canonical content lives in `04`–`16` and `01_product_doctrine.md`. Cited by L5 plan in its reference list (`plans/L5_policy_engine.md` final entry). After this session, move to `archive/` once X4 confirms no remaining extractions are needed.

**Coordination:** no active reconciliation; coordinator decision stands.

---

## 3. `aether_next_session_planning_prompt.md`

**Inbox:** 231 lines. This is **the prompt that kicked off this very session** — the "Aether next-session planning" directive with locked doctrine, locked decisions, deliverables list, required content handling, output format, and quality bar.

**Canonical equivalent:** operationally superseded by:
- `SESSION_START_SUMMARY_2026-04-18b.md` (locked decisions applied),
- `plans/00_ORCHESTRATION_MAP.md` (operating model + roster + dependencies),
- all 11 prompts in `prompts/` (per-agent one-shots).

**Differences:** the inbox prompt is a single monolithic brief; the canonical deliverables it asked for now exist as structured artifacts.

**Contradictions:** none — this session fully executed the prompt.

**Disposition:** **keep as reference only.** Historical provenance — proves what was asked for and when. Do not delete; future audits of session intent vs output will want to read both. Move to `archive/` after session-end index is signed.

**Coordination:** none needed; kickoff artifact.

---

## 4. `aether_oss_preview_roadmap.md` vs canonical `roadmaps/aether_oss_preview.md`

**Inbox:** 169 lines. 4-phase structure (Phase 0 definition/design → Phase 1 shippable preview core → Phase 2 speech/avatar → Phase 3 trust/polish). Recommended stack is Tauri + React + Rust + Python sidecar, with MuseTalk / TalkingHead / Wav2Lip as avatar baselines, Parakeet / Whisper / Moonshine STT, XTTS-v2 TTS. Heavy `[cite:NN]` usage.

**Canonical:** 358 lines. Same 4-phase structure, substantively aligned. Richer: explicit exclusions, primary-users section, experience goals, showcase structure, failure-mode list, Gemma 4 as default local LLM, deep 3D neumorphic monochrome direction, 548+-test-parity posture.

**Differences:**
- Inbox does **not** mention Gemma 4 (pre-dates the lock).
- Inbox does **not** mention deep 3D neumorphic monochrome design direction.
- Canonical adds: failure modes, exclusions list, showcase chapters, teaser-surface pattern, explicit 50% VRAM at Enhanced.
- Agent C noted (in earlier report): "substantively aligned with canonical (same 4-phase structure, same tech stack); canonical is richer; no content conflicts."

**Contradictions:** none substantive. Inbox's stack recommendations align with Tauri doctrine and the canonical Pro stack.

**Disposition:** **keep as reference only** — canonical is the source of truth. Agent C has already surfaced this in `plans/02_oss_preview_alignment_map.md` and treats canonical as authoritative. After session close, retire to `archive/`.

**Coordination:** Agent C (OSS alignment map) has already reconciled; no further work needed.

---

## 5. `aether_pro_roadmap.md` vs canonical `roadmaps/aether_pro.md`

**Inbox:** 226 lines. 7-phase structure (Phase 0 doctrine/arch lock → Phase 6 highest-tier companion quality). **Lists 7 strategic moat layers** (conversation timing engine + memory kernel + model router + policy engine + onboarding/trust UX + persona compiler + presence controller). Heavy `[cite:NN]` usage.

**Canonical:** 362 lines. Same 7-phase structure, substantively aligned. **Lists 8 must-own moat layers** per `01_product_doctrine.md` (reflex router / interaction state machine is broken out separately from timing). Richer: explicit failure modes, UI direction (deep 3D neumorphic monochrome), Gemma 4 lock, full tech-stack block, cross-reference index.

**Differences:**
- **Moat-layer count:** inbox says 7 (folds reflex into timing); canonical says 8 (reflex separate).
- Inbox does not mention Gemma 4.
- Canonical adds cross-references, failure modes, Don's UI preference, deeper Phase 1–6 task lists.

**Contradictions:**
- **Inbox 7 vs canonical 8.** Resolved by this session's `[DECIDED 2026-04-18]` layer-count lock (see `OPEN_QUESTIONS.md` and `plans/00_ORCHESTRATION_MAP.md` §1): **7 is now the working truth.** Inbox is correct on cardinality; canonical doctrine will be updated in the next pass to reflect 7 layers with reflex explicitly embedded in L1.
- Agent C flagged this already in `plans/01_pro_phase_crosswalk.md` and `plans/02_oss_preview_alignment_map.md`.

**Disposition:** **keep as reference only.** Canonical remains source of truth for Pro roadmap; the cardinality lock happened at planning level (not roadmap level), so canonical needs a doctrine-update pass to restate the 8 layers as 7. That doctrine-update pass is on the recommended-next-session list. Until then, canonical stands with the 7-vs-8 reconciliation note in `OPEN_QUESTIONS.md` providing the authoritative interpretation.

**Coordination:** Agent C already reconciled in planning docs. Coordinator schedules the doctrine-update pass.

---

## Summary table

| File | Lines | Canonical counterpart | Key conflict | Disposition |
|---|---|---|---|---|
| `aether_sources_matrix.md` | 155 | `sources_matrix.md` (170 lines) | None substantive | **merge into canonical** (pull "Why used" column) |
| `aether_cross_systems_spec.md` | 123 | `04`–`16` (absorbed) | Inbox doctrine softer than `01` | **keep as reference only** |
| `aether_next_session_planning_prompt.md` | 231 | Superseded by orchestration map + prompts | None — session executed it | **keep as reference only** |
| `aether_oss_preview_roadmap.md` | 169 | `roadmaps/aether_oss_preview.md` (358 lines) | None substantive; canonical richer | **keep as reference only** |
| `aether_pro_roadmap.md` | 226 | `roadmaps/aether_pro.md` (362 lines) | **7 vs 8 moat layers** (inbox 7 now locked as truth) | **keep as reference only**; doctrine update pending |

---

## Retirement plan

After `SESSION_END_INDEX_2026-04-18b.md` is signed:

1. Execute the "Why used" merge into `sources_matrix.md` (§1 disposition).
2. Move all 5 inbox files to `archive/inbox_2026-04-18b/` with a short README stating dispositions.
3. Schedule the doctrine-update pass (`01_product_doctrine.md` + `MASTER_OUTLINE_TREE.md`) to reflect the 7-layer model — not in this session.

No inbox file is deleted. Provenance is preserved.
