<!-- Thanks for contributing. This template is short on purpose. Please keep it. -->

## Summary

<!-- One or two sentences on what this PR changes and why. -->

## Linked issue

<!-- "Fixes #NN" or "Refs #NN". If there is no issue yet, add one — PRs that
appear without a matching issue are usually asked to slow down. -->

## Kind of change

- [ ] Docs / planning / wave-report only
- [ ] Tests only
- [ ] Governance / tooling (`tools/lint-*`, CI)
- [ ] Engine logic — layer: L1 / L2 / L3 / L4 / L5 / L6 / L7
- [ ] Shared infra (`event-bus`, `storage`, `telemetry`, `types`, `ui-kit`,
      `media-engine`)
- [ ] Architecture change (requires a prior `DECISION_LOCK_PASS_*.md` entry)

## Checklist

- [ ] I read `CONTRIBUTING.md` and the relevant interface pack under
      `planning/plans/implementation_prep/`.
- [ ] Tests added or updated, and I have run them locally.
- [ ] Docs updated: README / planning / wave report as applicable.
- [ ] Seven-layer boundary respected. Sibling `packages/l*-*` crates do not
      import each other in this PR.
- [ ] L5 is still the single writer for side-effectful actions. Nothing in
      this PR performs file / network / subprocess work outside the L5
      approved execution path.
- [ ] No Isabelle-tagged / private assets added to public distributables.
- [ ] Commit messages follow `<type>(<scope>): short imperative summary`.

## How to verify

<!-- Commands reviewers can run. Typical entries:
    pnpm -r --if-present typecheck
    cargo check --workspace
    cargo test -p aether-l5-policy
    cargo test -p aether-storage
-->

```
```

## Wave report (if this PR is part of a wave)

- [ ] Not part of a wave
- [ ] Wave report added / updated at the repo root — file name:

## Screenshots / logs (optional)

<!-- For UI PRs, docs-site PRs, or visible test output. -->
