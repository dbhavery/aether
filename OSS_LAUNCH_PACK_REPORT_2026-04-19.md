# OSS Launch Pack — Execution Report

**Date:** 2026-04-19
**Session:** Stabilization / Return-to-Plan — OSS Launch Pack phase
**Scope:** community-docs surface and GitHub templates required before any
public publication session.

---

## 1. Files created or updated

### Root-level community docs (new)

- `CODE_OF_CONDUCT.md` — adopts **Contributor Covenant v2.1** by reference
  rather than pasting the full text. Rationale in §3 below.
- `SECURITY.md` — in-scope / out-of-scope list, report channels (GitHub
  private advisory preferred, `@dbhavery` DM fallback), disclosure timeline,
  safe-harbor clause.
- `SUPPORT.md` — channel matrix (Bug / Feature / Docs / Security / CoC),
  what is and is not promised during the preview, "before opening an issue"
  checklist, good-first-reads list.
- `ROADMAP.md` — completed waves (W0 through W4 + W3.5), prioritized next
  steps, "not on the roadmap" exclusion list so scope creep is explicit.

### Root-level community docs (updated)

- `CONTRIBUTING.md` — carried forward from the untracked file produced in
  the prior session; no further edits required this pass (content already
  aligned with doctrine).

- `README.md` — reconciled after Wave 3.5:
  - Status block switches Wave 3.5 from `0%` to `100%` with honest
    sub-statement that L5 backends are still in-memory.
  - "What runs today" rewritten to reflect `cargo check --workspace` and
    `cargo test --workspace` both green, with per-crate test counts.
  - "What does not run yet" keeps L5 in-memory / no end-to-end loop wording.
  - Roadmap triage list drops the old Wave 3.5 slot and promotes
    "L5 durable persistence" as the real follow-up.
  - Getting Started snippet drops the "expected to surface wire-up gaps"
    disclaimer now that both commands are green.

### Docs tour (new)

- `docs/REPO_TOUR.md` — fifteen-minute guided walk. Points contributors at
  the authoritative planning docs first, then at `packages/l5-policy/` as
  the richest code surface.

### GitHub templates (new)

- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`
- `.github/ISSUE_TEMPLATE/docs_request.md`
- `.github/ISSUE_TEMPLATE/config.yml` — disables blank issues; provides
  security / CoC / support / contributor-guide contact links.
- `.github/PULL_REQUEST_TEMPLATE.md` — checkboxes for tests, docs, layer
  boundary, L5-single-writer, no-private-asset-leak, commit-message format.

### Not touched this pass (intentional)

- `.github/CODEOWNERS` — left as-is. The Wave 4 commit already wrote engine
  ownership lines.
- `.github/workflows/ci.yml` — legacy v1.0 Python CI. Re-tuning is deferred
  to the next session (Final Pre-Publication Hardening + Push + Handoff).
  Calling this out now so README does not mislead future contributors.
- `planning/` — no planning-doc edits. Launch-pack work is public-surface
  only.

---

## 2. Cross-checked README references

Every file the README now points at exists:

| README reference | File path | Status |
|---|---|---|
| `CONTRIBUTING.md` | `CONTRIBUTING.md` | present |
| `SECURITY.md` | `SECURITY.md` | present |
| `SUPPORT.md` | `SUPPORT.md` | present |
| `CODE_OF_CONDUCT.md` | `CODE_OF_CONDUCT.md` | present |
| `ROADMAP.md` | `ROADMAP.md` | present |
| `docs/REPO_TOUR.md` | `docs/REPO_TOUR.md` | present |
| `planning/00_VISION_AND_GUARDRAILS.md` | same | present |
| `planning/01_product_doctrine.md` | same | present |
| `planning/plans/00_ORCHESTRATION_MAP.md` | same | present |
| `planning/plans/implementation_prep/` | same (directory) | present |
| `WAVE3_EXECUTION_REPORT_2026-04-19.md` | same | present |
| `WAVE4_EXECUTION_REPORT_2026-04-19.md` | same | present |
| `LICENSE` | same | present (MIT, `Cargo.toml` now matches) |

No broken internal links remain in the README.

---

## 3. Decisions and template rationale

### 3.1 Code of Conduct — link-by-reference, not paste

The prior session's Write was rejected by an upstream content filter on the
verbatim Contributor Covenant enumeration. The filter-safe alternative is a
short wrapper that:

- names the version adopted (Contributor Covenant v2.1),
- links to the canonical text on `contributor-covenant.org`,
- documents the scope, reporting channels, enforcement posture, and
  attribution.

Legal effect is the same — the covenant is adopted by reference, which is
explicitly supported by the Contributor Covenant attribution guidance. The
rendered file avoids the enumerated-harms paragraph that triggered the
filter. A private reporting email is left as a `TODO (Don)` comment in the
file; GitHub DM and private vulnerability reporting serve as the interim
channels.

### 3.2 Issue template set: `bug`, `feature`, `docs`

Three templates keep triage honest without overwhelming contributors:

- **bug_report.md** collects environment (OS, `rustc --version`, commit SHA,
  affected layer), reproduction, expected vs. actual, and a docs-update
  checkbox. The docs-update box is there because "the docs were wrong" is
  a frequent contributor entry point and deserves a first-class channel.
- **feature_request.md** distinguishes engine first-logic slices, shared
  infra, governance, docs, and architecture proposals. Architecture
  proposals get their own sub-section that asks for reversibility
  classification and the planning doc being changed — this matches the
  `DECISION_LOCK_PASS_*.md` workflow already in use.
- **docs_request.md** categorizes factual / outdated / missing / confusing /
  broken-link issues and invites the contributor to open a small doc PR
  themselves as the friendliest first contribution.

`config.yml` disables blank issues and provides four contact links:
security advisory, CoC, support, contributor guide. Blank-issue submissions
tend to skip the repro-steps discipline the templates enforce.

### 3.3 PR template: boundary + L5-single-writer checks

The PR template's non-negotiable checklist items are the ones that the
project's `CLAUDE.md` enumerates as block-the-PR violations:

- layer-boundary respected (no sibling `l*-*` cross-imports),
- L5 remains the single writer for side effects,
- no Isabelle-tagged assets in public distributables.

Contributors can tick these truthfully without jumping through a full
governance review, and reviewers have a consistent checklist.

---

## 4. Open TODOs for Don

| # | Item | Why it was left for later |
|---|---|---|
| 1 | Dedicated reporting email address in `CODE_OF_CONDUCT.md` and `SECURITY.md` | Requires a real mailbox; GitHub DM + private advisory are the interim channels. Marked as `TODO (Don)` inline. |
| 2 | Re-tune `.github/workflows/ci.yml` off the legacy Python tree | Out of scope for a docs-pack session. Planned for the Final Pre-Publication Hardening + Push + Handoff session per the reconciliation report. |
| 3 | Decide public vs. private-preview posture before first push | This session intentionally does not push to origin. The launch-pack is ready; the decision on when to flip the GitHub repo back to public is Don's. |
| 4 | Opt-in enable GitHub Discussions | `SUPPORT.md` hints at it; currently the single public surface is Issues. Can be enabled once traffic justifies it. |
| 5 | Add a security reporting email or form (see TODO in `CODE_OF_CONDUCT.md`) | Related to #1 but narrower — only affects the SECURITY flow. |

None of these block the next session; all are additive.

---

## 5. Acceptance check against the session brief

- [x] `CODE_OF_CONDUCT.md` created, filter-safe.
- [x] `SECURITY.md`, `SUPPORT.md`, `ROADMAP.md` created.
- [x] `docs/REPO_TOUR.md` created.
- [x] `.github/ISSUE_TEMPLATE/{bug_report.md, feature_request.md, docs_request.md, config.yml}` created.
- [x] `.github/PULL_REQUEST_TEMPLATE.md` created.
- [x] `README.md` reconciled; every referenced file exists.
- [x] `CONTRIBUTING.md` finalized and committed-ready.

Launch-pack phase is **complete**.
