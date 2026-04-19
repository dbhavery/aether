# Session Recovery Checkpoint — 2026-04-19

**Audit mode only.** No files moved, edited, or scaffolded. This report is the single artifact produced.

---

## Current filesystem truth

### `file:///C:/Users/dbhav/Projects/aether/`

- Exists. Git repo on branch `dev`. Last commit `679e66c [DOCS] Distribution playbook for v1.0.0-pre launch` (2026-04-18, pre-retraction era).
- `git status --short`: **one untracked file only** — `scripts/generate_showcase_scenes.py`. No modifications, no staged changes.
- **Shape is the OLD v1.0 codebase**, not the monorepo shell. Top-level contents:
  - Python/desktop code: `src/` (agents, android, avatar, brain, core, desktop_legacy, main.py, memory, onboarding, persona, personas, shared, tools, voice), `desktop/`, `frontend/`, `personas/`, `scripts/`, `tests/`, `configs/`, `data/`, `logs/`.
  - Root files: `README.md` (v1.0 public-preview copy), `RUNWAY.md`, `LICENSE`, `pyproject.toml`, `requirements.txt`, `requirements-voice.txt`, `.env.example`, `.gitignore`.
  - Tooling: `.claude/`, `.superpowers/`, `.playwright-cli/`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, `.github/`.
  - `docs/`: `ARCHITECTURE-V2.md`, `DISTRIBUTION.md`, `LLM-PROVIDERS.md`, `ONBOARDING-SPEC.md`, `PERSONA-SCHEMA.md`, `PRODUCT-PLAN.md`, `SYNC-ISABELLE.md`, `superpowers/`.
- **Does NOT exist** (monorepo-shell targets per Wave 0 plan): `planning/`, `packages/`, `apps/`, `infra/`, `tools/`, `research/`.
- **No Wave reports exist** anywhere in the repo. None of the following were found:
  - `WAVE0_ASSIMILATION_REPORT_2026-04-19.md`
  - `WAVE0_EXECUTION_REPORT_2026-04-18.md`
  - `WAVE1_EXECUTION_REPORT_2026-04-18.md`
  - `WAVE2_EXECUTION_REPORT_2026-04-18.md`
  - `EARLY_ENGINE_STUB_WAVE_REPORT_2026-04-18.md`

### `file:///C:/Users/dbhav/Projects/aether-planning/`

- Exists. **Not a git repo** (unversioned workspace). All planning artifacts present and intact.
- Top-level (28 `.md` files + subdirs):
  - Numbered spec `01_` through `18_` (doctrine, family, vision, UX, architecture, memory, avatar, trust, tiers, updates, tech-stack, persona schema, model router).
  - `README.md`, `MASTER_OUTLINE_TREE.md`, `NUMBERED_SPEC.md`, `COMPARISON_REPORT.md`, `sources_matrix.md`.
  - `HANDOFF_2026-04-18.md`, `SESSION_START_SUMMARY_2026-04-18b.md`, `SESSION_END_INDEX_2026-04-18b.md`, `INBOX_RECONCILIATION_2026-04-18b.md`.
  - `DECISION_LOCK_PASS_2026-04-18c.md` (present, Wave 0 GO verdict locked).
  - `OPEN_QUESTIONS.md` (present).
  - `archive/` — `PULL_STATUS_2026-04-18.md`, `v1.0.0-pre_release_snapshot.json`.
  - `inbox_2026-04-18b/` — 5 source files carried forward.
  - `planning/` — `monorepo_plan_draft.md` (only file).
  - `plans/` — `00_ORCHESTRATION_MAP.md`, `01_pro_phase_crosswalk.md`, `02_oss_preview_alignment_map.md`, `03_content_lock_v1_port.md`, `IMPLEMENTATION_PREP_INDEX.md`, `L1_L4_L5_L7_integration_notes.md`, `L2_L3_L6_integration_notes.md`, L1–L7 system designs + L1–L7 top-level plans, `X3_tauri_architecture.md`, and `implementation_prep/` with 7 interface packs + `event_contracts_master.md` + `sqlite_schema_pack.md` + `test_matrix_master.md` + `implementation_handoff_notes.md`.
  - `prompts/` — `X1_repo_restructure.md`, `X2_isabelle_migration.md`, `X3_tauri_architecture.md`, `X4_v1_content_port.md`, plus L1–L7 prompts (L5 has both `L5_policy_engine.md` and `L5_policy_engine_system_design.md`).
  - `roadmaps/` — per-product roadmaps.

### Was planning imported into `aether/planning/`?

**No.** `aether/planning/` does not exist. The planning corpus is still at `aether-planning/` and unversioned. Wave 0 Step 4 ("move aether-planning/ into planning/ via git subtree add") has not been executed.

---

## Completed work

Verified on disk:

- **All planning artifacts** in `aether-planning/` are in place and complete (26+ files per HANDOFF_2026-04-18.md inventory; actual count ≥28).
- **5 control-plane decisions locked** in `DECISION_LOCK_PASS_2026-04-18c.md` (coordinator-recommended, pending Don ratification): `Decision::NeedsUpgrade` encoding, `DraftOnly` source discriminant, 3 missing L5 IPC commands, per-step re-eval rule, BYOK cap re-arm flow.
- **X1 Wave 0 readiness checklist**: all blocking items ticked; verdict "Wave 0 readiness: GO".
- **Scaffold-readiness** checklists for `packages/event-bus`, `packages/storage`, `packages/l5-policy`: all "Scaffold readiness: GO" (pending Wave 0 shell).
- **v1.0 public pull** fully executed 2026-04-18 (GitHub release+tag deleted, `dbhavery/aether` made private, portfolio entry removed via commit `d4cde07`, LinkedIn post deleted, snapshot archived at `archive/v1.0.0-pre_release_snapshot.json`).
- **v1.0 content ported forward**: `17_persona_pack_schema.md`, `18_model_router_spec.md`.
- **`aether/` repo v1.0 codebase**: present and last touched 2026-04-18 (pre-retraction). Last commits are the public-launch README + distribution playbook — effectively frozen.

---

## Partial work

- **Not truly partial** — the planning phase fully landed; implementation phase (X1 Wave 0) has not started. The boundary is crisp.
- Arguably partial: the HANDOFF_2026-04-18.md still lists 5 open blocking questions for the next session (segmentation axis, Tauri vs pywebview, Isabelle migration, repo structure, local sibling dirs). `DECISION_LOCK_PASS_2026-04-18c.md` resolves several downstream decisions but does not formally close all 5 handoff questions. Evidence: `OPEN_QUESTIONS.md` is 25,010 bytes — large, likely still carries open items. (Not re-read exhaustively this audit; flagged as uncertain.)
- **Uncommitted work in `aether/`**: single untracked file `scripts/generate_showcase_scenes.py`. Source/intent unclear — does not appear tied to any Wave plan; may be stray from a prior session.

---

## Not started

- **X1 Wave 0 — Monorepo Genesis.** No evidence of execution:
  - No `apps/`, `packages/`, `infra/`, `tools/`, `planning/`, `research/` directories at the repo root.
  - No `Cargo.toml` workspace, no `pnpm-workspace.yaml`, no `rust-toolchain.toml`.
  - No `CODEOWNERS`, no `CLAUDE.md` at the Aether repo root (user-level CLAUDE.md at `C:/Users/dbhav/.claude/CLAUDE.md` is global).
  - No Wave 0 execution/assimilation report.
- **Wave 1** (`packages/event-bus` + `packages/types` + `packages/storage` scaffolds) — not started.
- **Wave 2** (`packages/l5-policy` scaffold) — not started.
- **Early engine stub wave** — not started.
- **X2 Isabelle migration, X4 v1 content port** — prompts written, execution not started.

---

## Decision state

Locked doctrine still governing the next step (from `HANDOFF_2026-04-18.md` + `DECISION_LOCK_PASS_2026-04-18c.md`):

- No close-enough SaaS for core experience layers.
- OSS Preview may use OSS components; Aether Pro primarily custom-written. 8 must-own layers.
- Gemma 4 is default local LLM. 50% VRAM default for Full/Pro.
- Isabelle = privileged profile on Aether Pro, not separate codebase.
- **Monorepo baseline locked** (`planning/monorepo_plan_draft.md` status: working).
- **Tauri long-term doctrine locked; G1 approved.**
- 7-layer-to-package mapping locked.
- Shared-infra packages enumerated: `event-bus`, `types`, `ui-kit`, `media-engine`, `storage`, `telemetry`.
- 5 control-plane decisions coordinator-locked 2026-04-18c (pending Don ratification).
- **X1 Wave 0: GO**.

**Option B / plain copy active path?** The `aether-planning/planning/monorepo_plan_draft.md` recommends `git subtree add` (preserve history) as the default for importing `aether-planning/` into `aether/planning/`, with a flat-copy fallback option. No explicit "Option A vs Option B" selection is recorded on disk in the files I reviewed. **If "Option B / plain copy" was decided in-session, that decision is not visible in disk artifacts** — flag as uncertain and confirm with Don before acting.

---

## Resume point

**Next session: X1 Wave 0 — Monorepo Genesis** (coordinator + X1 agent, ~1 session).

**Exact first task:** resolve the repo-shell collision. The existing `file:///C:/Users/dbhav/Projects/aether/` already contains the retracted v1.0 Python codebase on branch `dev`. Wave 0 plan calls for creating a fresh monorepo shell at that same path. Before any Cargo/pnpm init:

1. Decide one of:
   - **(a)** Rename/move existing `aether/` → `aether-v1-archive/` (or similar), then create fresh monorepo at `aether/`.
   - **(b)** Create a new branch in existing `aether/` repo (e.g., `wave0/monorepo-genesis`), `git rm` the v1.0 code, and scaffold monorepo in-place — preserves the GitHub repo identity + history.
   - **(c)** Scaffold the monorepo at a different path (e.g., `aether-monorepo/`) and retire `aether/` later.
2. Confirm "plain copy" vs `git subtree add` for `aether-planning/` → `planning/` import.

Only after (1) and (2) are confirmed can the six Wave 0 scope items (workspace manifests, empty top-level dirs, planning import, root `README.md`/`CLAUDE.md`/`CODEOWNERS`/`.gitignore`) execute.

---

## Risks / conflicts

- **Path collision**: `aether/` is occupied by the v1.0 codebase. Every Wave 0 plan artifact assumes this path is the monorepo root; nothing on disk documents how to resolve the collision. Executing Wave 0 naively would conflict with or overwrite the v1.0 tree.
- **History preservation ambiguity**: plan default is `git subtree add`; user prompt mentions "Option B / plain copy". These conflict. Disk evidence does not settle it.
- **`OPEN_QUESTIONS.md` not re-read exhaustively** in this audit. It may already contain `[DECIDED 2026-04-XX]` locks for items HANDOFF flagged as open (Tauri, Isabelle migration, repo structure, segmentation, siblings). The next session should re-read it in full before acting.
- **Untracked `scripts/generate_showcase_scenes.py`** in `aether/` — unclear provenance; review and decide (commit / discard / move aside) before any destructive Wave 0 operation.
- **Sibling repos** `aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/` exist on disk (per HANDOFF_2026-04-18.md). Their fate is a "still open, non-blocking" item — but they should be identified and tagged before Wave 0 to avoid accidental inclusion.
- **`aether-planning/` is unversioned.** If `git subtree add` is chosen, it must first be `git init`ed and committed, or adapted. This is not called out in the monorepo plan and could trip Wave 0.
- **Conflict between handoff doctrine and global memory**: `feedback_css_default_for_ui.md` (locked 2026-04-11) says pywebview; current plan locks Tauri G1. HANDOFF notes this; needs one-line reconciliation in the global feedback memory before Wave 0 executes to avoid future drift.

---

## Recommended next prompt

Paste this into a fresh Claude Code session:

```
X1 Wave 0 — Monorepo Genesis (execute). Crash-recovery audit at
file:///C:/Users/dbhav/Projects/aether/SESSION_RECOVERY_CHECKPOINT_2026-04-19.md
shows Wave 0 has NOT started. Existing aether/ still holds the retracted
v1.0 Python codebase on branch `dev`; the monorepo shell does not exist.

Before executing Wave 0, resolve two gates with me:

GATE 1 — Repo shell collision. Pick one:
  (a) rename existing aether/ -> aether-v1-archive/, create fresh monorepo at aether/
  (b) new branch on existing aether/ repo, git rm v1.0 tree, scaffold monorepo in-place
      (preserves GitHub identity + history)
  (c) scaffold monorepo at a different path

GATE 2 — Planning import:
  (a) git subtree add (preserve history; requires aether-planning/ be git-inited first)
  (b) plain copy (flat import, no history)

Read these first, in order:
  - file:///C:/Users/dbhav/Projects/aether/SESSION_RECOVERY_CHECKPOINT_2026-04-19.md
  - file:///C:/Users/dbhav/Projects/aether-planning/HANDOFF_2026-04-18.md
  - file:///C:/Users/dbhav/Projects/aether-planning/DECISION_LOCK_PASS_2026-04-18c.md  (Wave 0 = GO)
  - file:///C:/Users/dbhav/Projects/aether-planning/OPEN_QUESTIONS.md  (re-read in full; identify
    any [DECIDED 2026-04-XX] locks for Tauri/Isabelle/repo-structure/segmentation/siblings)
  - file:///C:/Users/dbhav/Projects/aether-planning/planning/monorepo_plan_draft.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md
  - file:///C:/Users/dbhav/Projects/aether-planning/prompts/X1_repo_restructure.md

Do NOT touch v1.0 files until I confirm Gate 1. Do NOT import planning until I
confirm Gate 2.

After gates confirmed, execute Wave 0 scope:
  1. Cargo workspace manifest, package.json + pnpm-workspace.yaml, rust-toolchain.toml
  2. apps/ packages/ infra/ tools/ planning/ research/ docs/ personas/ with README stubs
  3. Planning import per Gate 2
  4. Root README.md, CLAUDE.md (AI-agent ops rules), CODEOWNERS, .gitignore
  5. Write WAVE0_EXECUTION_REPORT_2026-04-19.md documenting every path created/copied/moved
  6. Stop. No Wave 1 until I approve.

Also: one untracked file in aether/ — scripts/generate_showcase_scenes.py. Tell me what
it is; do not commit it as part of Wave 0.

Doctrine guardrails (non-negotiable, from 01_product_doctrine.md):
  - No close-enough SaaS for core experience layers
  - Must-own layers (8): presence, memory kernel, model router, reflex router, policy
    engine, persona compiler, timing, trust UX
  - Gemma 4 default local LLM; 50% VRAM full/pro
  - Tauri G1 locked (reconcile feedback_css_default_for_ui.md accordingly)

Clickable file links only (file:///C:/... forward slashes). Direct, no fluff.
```

---

## Final response (answers to the four audit questions)

1. **Where progress actually stopped:** at the end of the planning phase on 2026-04-18. `DECISION_LOCK_PASS_2026-04-18c.md` declared "Wave 0 readiness: GO" and the very-next-session scope, but no implementation file, directory, or Wave 0 report has been created. No files in `aether/` have been touched since 2026-04-18 (pre-retraction commits), aside from one stray untracked script.
2. **Wave 0 assimilation status:** **never started.** No `planning/`, `packages/`, `apps/`, `infra/`, `tools/`, `research/` dirs in `aether/`. No Wave 0 report exists. `aether-planning/` is untouched and not yet imported.
3. **Is the next step still revised Wave 0, or something later?** **Still Wave 0** — specifically, resolve the two gates (repo-shell collision + import method), then execute the 6-step Wave 0 scope. No earlier work is missing; no later work is ready to leapfrog into.
4. **Path of this checkpoint report:** `file:///C:/Users/dbhav/Projects/aether/SESSION_RECOVERY_CHECKPOINT_2026-04-19.md`
