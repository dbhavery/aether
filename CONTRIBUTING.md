# Contributing to Free Aether — Community Edition

Thank you for considering a contribution. This document explains what kinds of
contributions help, how the work is organized, and what to expect from review.

Aether is an architecture project in an early preview state. That means the
**contract surfaces matter more than the visible product**. Most of the
high-leverage work right now is invisible to end users: docs, lints, test
matrices, contract refinements, first-logic slices.

---

## 1. Before you start

1. Read `planning/00_VISION_AND_GUARDRAILS.md`. This is doctrine. If your idea
   conflicts with it, open an issue before writing code.
2. Read `planning/01_product_doctrine.md` for the hard rules.
3. Read `planning/plans/00_ORCHESTRATION_MAP.md` to understand how the seven
   layers relate.
4. Skim the most recent `WAVE*_EXECUTION_REPORT_*.md` to see where the project
   actually is today.
5. Check [Open Questions](planning/OPEN_QUESTIONS.md) and existing issues
   before proposing anything substantial.

---

## 2. What to work on

### For first-time contributors

- **Docs fixes.** Typos, broken links, ambiguous passages in planning files.
- **README / CONTRIBUTING / SUPPORT improvements.** Clarity helps everyone.
- **Test expansions.** Each layer has a `tests/smoke.rs` that could be much
  deeper. `packages/l5-policy/tests/engine_slice.rs` is the richest example.
- **Linter / governance tooling.** The scaffolds under `tools/` need real
  rules — `cargo-deny` bans, ESLint rules, policy-bypass detection.
- **CI.** The existing `.github/workflows/ci.yml` is tuned to the legacy v1.0
  Python tree and needs a pass for the Rust + pnpm workspace.

### For deeper contributors

- **Wave 3.5** — rusqlite wire-up in `packages/storage`, swap L5's in-memory
  backends behind a feature flag. See Wave 3 report §2 for the locked design.
- **Wave 4.1** — activate the `[bans]` block in
  `tools/lint-layer-boundaries/deny.toml`.
- **First-logic slices for L1/L2/L3/L4/L6/L7** — each layer has an interface
  pack in `planning/plans/implementation_prep/` that defines the target
  surface. Pick one, open an issue to claim it, produce a wave report.
- **`ts-rs` bindings generator** under `tools/ts-bindings-gen/` so
  `packages/l5-policy-ts/` becomes generated instead of hand-written.

### What is out of scope right now

- Full feature work in `apps/desktop/` or `apps/guest/` before L5 persistence
  lands.
- Architecture rewrites, layer merges, or new top-level concepts. These
  require a `DECISION_LOCK_PASS_*.md` entry and maintainer review.
- Anything that adds a cross-layer `use` / `import` between sibling engine
  packages.

---

## 3. Workflow

### Claiming work

1. Find or open an issue that describes the change.
2. Comment to claim it (or ask a maintainer to assign).
3. For non-trivial work, sketch the approach in the issue **before** writing
   code. Review cycles are shorter when the design is agreed first.

### Branches

- Base your work on `dev`. Never push directly to `master`.
- Feature branches: `feature/<layer-or-area>/<short-slug>`.
- Docs-only branches: `docs/<short-slug>`.

### Commits

Commit messages follow the repo's existing pattern:

```
<type>(<scope>): short imperative summary

Optional body — what changed and why. Reference planning docs or wave
reports where relevant.
```

`<type>` is one of `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
`<scope>` is the package or area (`l5`, `engines`, `repo`, `tooling`, etc.).

Commits should be atomic. If a single change touches three layers, it is
probably three commits — or it is crossing a layer boundary and needs
rethinking.

### Tests

- New trait surfaces land with at least a smoke test asserting enum
  cardinality / constructor availability.
- New engine logic lands with integration tests mapped back to the
  `test_matrix_master.md` entries where relevant.
- Bug fixes include a regression test that fails before the fix and passes
  after.

### Docs-first policy for major changes

Anything that changes a **contract** — an event field, an enum variant, a
trait signature, a planning-doc decision — lands as docs first:

1. Propose in a PR that touches only `planning/` and the relevant
   `README.md` / interface-pack file.
2. Get maintainer review on the design.
3. Then open the implementation PR that materializes the decision in code.

This is slower. It is also how a seven-layer architecture stays coherent.

### When a wave lands

Whole waves (multi-day efforts that ship a logic slice across a layer) produce
a dated `WAVE*_EXECUTION_REPORT_YYYY-MM-DD.md` at the repo root. The report:

- Lists files created / modified.
- Calls out any deferred decisions or partial implementations.
- Updates the roadmap graphic at the bottom.
- Is honest about what was **not** done.

If your contribution is part of a wave, you and the reviewer agree on the
report up front so it gets written alongside the code, not six months later.

---

## 4. Proposing architecture changes

Architecture proposals follow a fixed shape:

1. Open an issue using the **Feature request** template and select the
   "architecture proposal" path.
2. Reference the specific planning doc(s) you would change.
3. State the reversibility cost — is this a one-way door? A two-way door?
4. Wait for a maintainer to invite a `DECISION_LOCK_PASS` update.
5. The decision lock is written first. The implementation follows.

Unilateral doctrine edits get closed without review. This is by design.

---

## 5. Reporting blockers honestly

If you hit a blocker — missing tooling, unclear contract, conflict between two
planning docs — say so. The project favors an accurate partial report over a
confident-sounding wrong one. The Wave 3 and Wave 4 execution reports both
contain explicit deferrals; emulate that style.

Examples of acceptable outcomes on a PR:

- "I scaffolded X but could not validate with `cargo check` because I don't
  have rustup installed on my CI environment — flagging so reviewers can run
  it."
- "I hit a contract conflict between L4 interface pack §3 and the event
  contracts master §7. I've paused implementation and opened issue #NN."

Examples that get pushed back:

- "Added silently removes the audit write under a flag" — policy bypass is
  never acceptable, even behind a flag.
- "Refactored while I was in there" — opportunistic refactors cause drift.

---

## 6. Reviews

Every PR is reviewed by a maintainer. Reviews will focus on:

- Does it match the interface pack / decision lock for the area?
- Does it respect the seven-layer boundary?
- Does L5 remain the single writer for side effects?
- Is the test coverage honest about what it actually proves?
- Are doc and report updates present?

Expect reviewers to ask you to split PRs, shrink scope, or push part of the
change into a planning-doc PR first.

---

## 7. Release cadence

The project is pre-0.1. There is no fixed release cadence yet. Waves land as
they are ready. Public tagged previews will begin once Wave 3.5 (persistence)
and at least one engine first-logic slice (L1 or L4) are merged.

---

## 8. Contact

- Issues: GitHub issue tracker on this repo.
- Security: see `SECURITY.md` — do not file public issues.
- Questions about doctrine: open a `question` issue or flag on the relevant
  planning doc.
