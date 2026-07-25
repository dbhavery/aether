---
name: Feature request
about: Propose a change in code, an engine slice, a lint rule, or an architecture change.
title: "[feat] "
labels: ["enhancement", "triage"]
assignees: []
---

## One-line summary

<!-- What you want, in one sentence. -->

## Kind of change

- [ ] Engine first-logic slice (specify layer: L1 / L2 / L3 / L4 / L6 / L7)
- [ ] Shared-infra improvement (`event-bus`, `storage`, `telemetry`, `types`,
      `ui-kit`, `media-engine`)
- [ ] Governance / tooling (`tools/lint-*`, `tools/ts-bindings-gen/`, CI)
- [ ] Documentation / planning doc refinement
- [ ] Architecture proposal (see section below)
- [ ] Other — describe:

## Motivation

<!-- Why does this matter now? Reference a wave report, planning doc, or a
pain you hit while contributing. "This would be cool" is not enough. -->

## Affected layer or package

<!-- Be specific. If it crosses more than one layer, this is probably two
issues or needs an architecture proposal. -->

## Proposed approach

<!-- A sketch, not a full design. Reviewers will push back on scope before
you invest in the full design. -->

## Backward compatibility

- [ ] No contract change (no event fields, no enum variants, no trait
      signatures touched)
- [ ] Additive contract change (new variant / new optional field / new
      method with default)
- [ ] Breaking contract change — requires `DECISION_LOCK_PASS_*.md` update

## Tests and docs

- [ ] I will add tests in the relevant matrix slot
- [ ] I will update the relevant planning doc / README / wave report
- [ ] I will open the docs PR first if this is an architecture proposal

## Architecture proposal (only if the box above is ticked)

- Planning doc(s) being changed:
- Reversibility: [ ] one-way door  [ ] two-way door
- Comparable prior decision (if any):
- Open questions you want the maintainer to weigh in on first:

## Extra context

<!-- Linked issues, prior art, screenshots, sketches. -->
