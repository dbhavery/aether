# Wave 0 — Monorepo Assimilation Report — 2026-04-19

**Mode:** Revised Wave 0 (Option B — adopt existing `aether/` as monorepo root, plain copy for planning import).
**Scope:** Additive assimilation only. No deletions. No overwrites. No Wave 1 scaffolding.

Upstream: [Session Recovery Checkpoint 2026-04-19](file:///C:/Users/dbhav/Projects/aether/SESSION_RECOVERY_CHECKPOINT_2026-04-19.md), [Monorepo plan draft](file:///C:/Users/dbhav/Projects/aether/planning/planning/monorepo_plan_draft.md), [Decision lock pass 2026-04-18c](file:///C:/Users/dbhav/Projects/aether/planning/DECISION_LOCK_PASS_2026-04-18c.md).

---

## 1. Monorepo directories created

All created at repo root `file:///C:/Users/dbhav/Projects/aether/`:

- `file:///C:/Users/dbhav/Projects/aether/apps/` (empty)
- `file:///C:/Users/dbhav/Projects/aether/packages/` (empty)
- `file:///C:/Users/dbhav/Projects/aether/infra/` (empty)
- `file:///C:/Users/dbhav/Projects/aether/tools/` (empty)
- `file:///C:/Users/dbhav/Projects/aether/planning/` (populated — see §2)
- `file:///C:/Users/dbhav/Projects/aether/research/` (empty)

Two monorepo buckets (`docs/`, `personas/`) already existed as legacy folders and were adopted in place with zero modifications.

## 2. Planning import

- **Method:** plain recursive copy via `cp -r aether-planning/. aether/planning/` (per Don's decision; subtree import declined).
- **Source:** `file:///C:/Users/dbhav/Projects/aether-planning/`
- **Destination:** `file:///C:/Users/dbhav/Projects/aether/planning/`
- **File-count parity:** 85 files in source, 85 files in destination. Parity confirmed.
- **Collisions:** none. Destination `planning/` did not exist prior to this wave; no pre-existing files could collide.
- **Top-level items imported (38 entries, `.md` + subdirs):**
  `01_product_doctrine.md` … `18_model_router_spec.md`, `README.md`, `COMPARISON_REPORT.md`, `DECISION_LOCK_PASS_2026-04-18c.md`, `HANDOFF_2026-04-18.md`, `INBOX_RECONCILIATION_2026-04-18b.md`, `MASTER_OUTLINE_TREE.md`, `NUMBERED_SPEC.md`, `OPEN_QUESTIONS.md`, `SESSION_END_INDEX_2026-04-18b.md`, `SESSION_START_SUMMARY_2026-04-18b.md`, `sources_matrix.md`, and subdirs `archive/`, `inbox_2026-04-18b/`, `planning/` (nested — monorepo_plan_draft + others), `plans/`, `prompts/`, `roadmaps/`.
- **History:** not preserved (plain copy; aether-planning/ was never a git repo anyway). Source directory `aether-planning/` remains intact on disk as the original.

## 3. Non-destructive guarantee

- **No legacy files deleted.** `src/`, `desktop/`, `frontend/`, `configs/`, `data/`, `logs/`, `scripts/`, `tests/`, root manifests, README/LICENSE/.gitignore all preserved exactly as they were before this wave.
- **No legacy files overwritten.** Planning import targeted a directory that did not pre-exist; no byte of legacy content was touched.
- **No files renamed or moved.**
- **Adopted in place (no changes):** `docs/`, `personas/`, `.github/`, `.claude/`, `.superpowers/`, root `README.md`, `LICENSE`, `.gitignore`, `.env.example`, `pyproject.toml`, `requirements.txt`, `requirements-voice.txt`, `RUNWAY.md`.
- **Legacy-root → monorepo-bucket mapping:** see [LEGACY_ROOT_MAPPING_2026-04-19.md](file:///C:/Users/dbhav/Projects/aether/planning/LEGACY_ROOT_MAPPING_2026-04-19.md).

## 4. Wave 1 readiness

**Ready.** The monorepo shell exists. Planning corpus is in-tree. Empty target directories (`apps/`, `packages/`, `infra/`, `tools/`, `research/`) are present to receive Wave 1 scaffolds.

Wave 1 scope per `planning/planning/monorepo_plan_draft.md` §5:
- `packages/event-bus/`, `packages/types/`, `packages/storage/`, `packages/ui-kit/`, `packages/media-engine/`, `packages/telemetry/` — typed stubs only.
- `tools/ts-bindings-gen/` — codegen scaffold.
- `tools/lint-layer-boundaries/`, `tools/lint-policy-bypass/`, `tools/lint-private-asset-leak/` — boundary-lint tooling, permissive rules initially.

Nothing in this wave blocks Wave 1. Scaffold-readiness GO verdicts in [DECISION_LOCK_PASS_2026-04-18c.md](file:///C:/Users/dbhav/Projects/aether/planning/DECISION_LOCK_PASS_2026-04-18c.md) remain valid.

## 5. Deferred cleanup (for later waves, not this one)

Non-blocking items surfaced during assimilation — handle in later waves, not now:

1. **Workspace manifests absent.** `Cargo.toml`, `pnpm-workspace.yaml`, `rust-toolchain.toml` — required at repo root before Rust/TS packages can compile. Blocks Wave 1 execution but not Wave 1 scaffold layout. Add as first Wave 1 task.
2. **Root `.gitignore` is Python-only.** Needs Rust (`target/`, `Cargo.lock` policy) and pnpm (`node_modules/`, `.pnpm-store/`) entries. Defer until Wave 1 adds those artifacts.
3. **Root `README.md`** is the retracted v1.0 public-preview copy. Monorepo plan calls for replacement pointing to `planning/README.md`. Defer to a later wave; do not overwrite yet.
4. **Root `CLAUDE.md`** not present. Monorepo plan calls for AI-agent operating rules at repo root. Defer to Wave 1.
5. **`CODEOWNERS`** not present. Required by guardrail §4.1(5). Defer to Wave 1 alongside agent ownership map.
6. **Legacy Python tree (`src/`, `desktop/`, `frontend/`, `tests/`, `scripts/`, `configs/`, `data/`, `logs/`, `pyproject.toml`, `requirements*.txt`)** remains in place. Triage plan: port capability-by-capability into `packages/l*-*/` during Waves 2–4 via X2 (Isabelle) and X4 (v1 content port); retire legacy paths only after parity.
7. **`docs/` content triage.** v1.0 `ARCHITECTURE-V2.md`, `PRODUCT-PLAN.md`, etc. may be partly superseded by `planning/` doctrine. L7 reconciliation pass needed later.
8. **`personas/` content reconciliation** against new `planning/17_persona_pack_schema.md`. L6 reconciliation pass.
9. **Untracked `scripts/generate_showcase_scenes.py`** still unclassified. Needs decision: commit / move to `tools/` / discard. Not blocking.
10. **Nested `planning/planning/`** — the imported corpus already has its own `planning/` subfolder (containing `monorepo_plan_draft.md`). This is preserved faithfully but creates the slightly awkward path `aether/planning/planning/monorepo_plan_draft.md`. Optional future flatten; document as-is for now to match upstream.
11. **Sibling repos** (`aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/`, `aether-planning/` itself) — fate still open. `aether-planning/` is now duplicated content; Don may archive/delete the original once the in-repo copy is confirmed canonical.
12. **Reconcile `feedback_css_default_for_ui.md`** (pywebview locked 2026-04-11) against current Tauri G1 doctrine before Wave 3 desktop shell work.
13. **`OPEN_QUESTIONS.md` re-read pass** — still 25 KB, may contain [DECIDED] locks not yet propagated. Read in full before Wave 2 layer work.

## 6. Git state

- Branch: `dev`
- All new artifacts (monorepo dirs, imported `planning/`, this report, legacy mapping doc) are **untracked**. No commits made in this wave (awaiting Don's go-ahead on commit strategy and message style).
- Pre-wave untracked `scripts/generate_showcase_scenes.py` and `SESSION_RECOVERY_CHECKPOINT_2026-04-19.md` still untracked; not touched.

---

## Resume prompt for Wave 1

```
Wave 1 — Shared infra scaffolds. Revised Wave 0 assimilation complete per
file:///C:/Users/dbhav/Projects/aether/WAVE0_ASSIMILATION_REPORT_2026-04-19.md.
Monorepo dirs exist, planning/ imported, nothing destructive.

Before scaffolding packages, land workspace manifests at repo root:
  - Cargo.toml (Rust workspace)
  - package.json + pnpm-workspace.yaml (pnpm workspace)
  - rust-toolchain.toml (pinned toolchain)
  - CLAUDE.md (agent ops rules)
  - CODEOWNERS

Then scaffold typed stubs only (no logic) in:
  - packages/event-bus/, packages/types/, packages/storage/,
    packages/ui-kit/, packages/media-engine/, packages/telemetry/
  - tools/ts-bindings-gen/, tools/lint-layer-boundaries/,
    tools/lint-policy-bypass/, tools/lint-private-asset-leak/

Confirm commit strategy with Don before staging anything.
```
