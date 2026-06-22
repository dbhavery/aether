# Support

Free Aether — Community Edition is an early-preview, single-maintainer project. This document explains where to ask what, and what level of support you can realistically expect during the preview.

## Where to ask what

| Kind of question                                   | Best channel |
|----------------------------------------------------|--------------|
| "I think I found a bug"                            | GitHub Issues, template: *Bug report* |
| "I want a feature / an engine slice / a lint rule" | GitHub Issues, template: *Feature request* |
| "Something in the docs or planning is wrong"       | GitHub Issues, template: *Docs request* |
| "How should I approach contributing?"              | Read `CONTRIBUTING.md`; if still unclear, open a Feature request with the *question* box checked |
| Security / policy-bypass concerns                  | Do **not** open a public issue. Follow `SECURITY.md` |
| Code of conduct concerns                           | Follow `CODE_OF_CONDUCT.md` |
| General "is this project active?" question         | Check the most recent `WAVE*_EXECUTION_REPORT_*.md` at the repo root — these are dated and dense; they are the honest signal |

GitHub Discussions may be enabled later. For now, Issues is the single public surface.

## What is promised

- Every in-scope issue gets an acknowledgment within one to two weeks.
- Security reports get acknowledgment within seven days (see `SECURITY.md`).
- Decisions that affect the architecture (the seven-layer design in `ARCHITECTURE.md` or the product rules in `docs/PRODUCT-PLAN.md`) are recorded as an ADR under `docs/adr/` and referenced from the relevant issue.

## What is not promised

- A fixed response SLA. This is a single-maintainer preview.
- A fixed release cadence. See `ROADMAP.md` for the rough ordering; dates intentionally absent.
- Backwards compatibility. Event contracts, trait signatures, and schema are still moving. Expect breakage until the first tagged preview.
- Non-English support today. English is the working language for the preview.
- Private one-on-one help. Please use public Issues so the answer helps the next person asking the same question; the exceptions are security and code-of-conduct channels described in their respective files.

## Before opening an issue

1. Search existing Issues — many questions already have an answer or a cross-link.
2. Skim the most recent wave execution report. Several "this doesn't work" reports turn out to be features that are explicitly deferred with a named future wave.
3. Check the ADR log under `docs/adr/` — it records the decisions already locked, so your question may already be answered there.
4. If you still have a question, open the matching template and fill in the environment / repro / layer fields. They exist to save a round-trip.

## Good first reads

- `README.md` — the honest project status block is in section 3.
- `CONTRIBUTING.md` — what kinds of PRs move the project forward.
- `docs/REPO_TOUR.md` — a short guided walk through the directories.
- `ARCHITECTURE.md` — how the seven layers fit together.

## Contact of last resort

If a channel above is unavailable (for example, GitHub Issues is temporarily disabled during a restructuring), reach the maintainer via https://github.com/dbhavery. Expect slower response than the public channels.
