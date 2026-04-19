# Legacy Root Mapping — 2026-04-19

Maps every current top-level entry in `file:///C:/Users/dbhav/Projects/aether/` to its monorepo bucket. Additive assimilation — nothing was moved, deleted, or overwritten.

## Monorepo top-level buckets (target layout per `planning/planning/monorepo_plan_draft.md` §1)

`apps/` · `packages/` · `infra/` · `tools/` · `planning/` · `research/` · `docs/` · `personas/`

## Current top-level inventory

| Current path | Kind | Maps to | Disposition |
|---|---|---|---|
| `apps/` | dir (new, empty) | `apps/` | Monorepo bucket — created this wave |
| `packages/` | dir (new, empty) | `packages/` | Monorepo bucket — created this wave |
| `infra/` | dir (new, empty) | `infra/` | Monorepo bucket — created this wave |
| `tools/` | dir (new, empty) | `tools/` | Monorepo bucket — created this wave |
| `planning/` | dir (new, populated) | `planning/` | Monorepo bucket — created + plain-copied from `aether-planning/` this wave |
| `research/` | dir (new, empty) | `research/` | Monorepo bucket — created this wave |
| `docs/` | dir (legacy, adopted) | `docs/` | **Adopted in place.** Contains v1.0 `ARCHITECTURE-V2.md`, `DISTRIBUTION.md`, `LLM-PROVIDERS.md`, `ONBOARDING-SPEC.md`, `PERSONA-SCHEMA.md`, `PRODUCT-PLAN.md`, `SYNC-ISABELLE.md`, `superpowers/`. Later wave: triage — some content may move to `planning/` (doctrine) or `research/archive/v1_docs/` (retired). |
| `personas/` | dir (legacy, adopted) | `personas/` | **Adopted in place.** v1.0 persona pack content. L6 to reconcile against `planning/17_persona_pack_schema.md` in a later wave. |
| `src/` | dir (legacy Python) | **unmapped** | v1.0 Python codebase (`agents/`, `android/`, `avatar/`, `brain/`, `core/`, `desktop_legacy/`, `main.py`, `memory/`, `onboarding/`, `persona/`, `personas/`, `shared/`, `tools/`, `voice/`). Deferred: port piecewise into `packages/l*-*/` during Waves 2–4 via X2/X4; then retire. |
| `desktop/` | dir (legacy) | **unmapped** | v1.0 desktop shell. Candidate target: `apps/desktop/` after Tauri scaffold in Wave 3 (X3). Do not touch this wave. |
| `frontend/` | dir (legacy) | **unmapped** | v1.0 frontend assets. Candidate targets: `apps/desktop/` (composed UI) and/or `packages/ui-kit/` (extracted primitives) in Waves 2–4 (L7). |
| `configs/` | dir (legacy) | **unmapped** | v1.0 runtime configs. Likely splits across `infra/` (deployment) and `apps/*/` (per-app config) in later waves. |
| `data/` | dir (legacy) | **unmapped** | v1.0 runtime data surface. Out of scope for monorepo; candidate for `.gitignore` hardening later. |
| `logs/` | dir (legacy) | **unmapped** | Runtime logs. Should already be `.gitignore`d; verify in a cleanup wave. |
| `scripts/` | dir (legacy) | **unmapped** | v1.0 scripts incl. untracked `generate_showcase_scenes.py`. Candidate target: `tools/` per-script after audit. |
| `tests/` | dir (legacy) | **unmapped** | v1.0 test suite. Tests should move with the source they cover during L* package ports (Waves 2–4). |
| `README.md` | file | root | **Preserved in place.** v1.0 public-preview copy. Monorepo plan calls for a replacement root README pointing to `planning/README.md` — deferred to a later wave to avoid overwrite. |
| `RUNWAY.md` | file | root | Preserved in place. Legacy planning artifact. |
| `LICENSE` | file | root | Preserved in place. Monorepo-compatible. |
| `pyproject.toml` | file | root | Preserved in place. Python-only, conflicts with target Rust/pnpm workspace roots; reconciled when X1 lands `Cargo.toml` / `pnpm-workspace.yaml` / `rust-toolchain.toml` (Wave 1 or follow-on). |
| `requirements.txt`, `requirements-voice.txt` | file | root | Preserved in place. Python runtime deps; scope-bounded to v1.0 code under `src/`. |
| `.env.example` | file | root | Preserved in place. |
| `.gitignore` | file | root | **Preserved in place.** Monorepo plan calls for a replacement `.gitignore` covering Rust/pnpm artifacts — deferred; do not overwrite. |
| `.github/` | dir | adopted | Carry forward PR/issue templates. Add `CODEOWNERS` in a later wave. |
| `.claude/`, `.superpowers/`, `.playwright-cli/` | dir | adopted | Agent tooling. In place. |
| `.venv/`, `.pytest_cache/`, `.ruff_cache/` | dir | ignored | Local caches. Out of monorepo scope. |
| `.git/` | dir | root | Monorepo git history (branch `dev`). Preserved. |
| `SESSION_RECOVERY_CHECKPOINT_2026-04-19.md` | file (untracked) | root | Audit artifact from checkpoint session. Keep for traceability; later-wave cleanup may move to `research/`. |
| `WAVE0_ASSIMILATION_REPORT_2026-04-19.md` | file (new) | root | This wave's deliverable. |

## Summary

- **Monorepo buckets created this wave:** `apps/`, `packages/`, `infra/`, `tools/`, `planning/`, `research/`.
- **Adopted in place:** `docs/`, `personas/`, `.github/`, root `README.md`/`LICENSE`/`.gitignore`/`.env.example`, root manifests.
- **Unmapped / deferred for later waves:** `src/`, `desktop/`, `frontend/`, `configs/`, `data/`, `logs/`, `scripts/`, `tests/`, `RUNWAY.md`, Python manifests.
- **No file was deleted, moved, or overwritten in this wave.**
