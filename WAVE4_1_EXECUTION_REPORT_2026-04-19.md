# Wave 4.1 — Layer-Boundary Enforcement — Execution Report

**Date:** 2026-04-19
**Mode:** Governance activation. No engine logic changes.
**Prerequisites:** Waves 0–4 committed; Wave 3.5 storage substrate;
final pre-publication hardening + push.

---

## 1. Scope

Wave 1 scaffolded `tools/lint-layer-boundaries/` with a `deny.toml`
placeholder and a README calling out the TODO. Wave 4.1 activates that
scaffold into a real, running linter that rejects any intra-workspace
dependency edge not on the doctrine allowlist.

Explicitly in scope:

- Analyze current `[dependencies]` / `[dev-dependencies]` edges across
  the seven engine crates and four shared-infra crates.
- Encode the doctrine allowlist in a tool that runs locally and in CI.
- Wire the tool into `.github/workflows/ci.yml` so violations block PRs.
- Update contributor docs so the rule, the tool, and the escape hatch
  are all discoverable.

Out of scope (explicitly deferred):

- `tools/lint-policy-bypass/` — detects direct executor calls outside
  `packages/l5-policy`. Still scaffold; a future wave.
- `tools/lint-private-asset-leak/` — fails builds if Isabelle-tagged
  content appears in public distributables. Still scaffold; a future
  wave.
- `tools/ts-bindings-gen/` — TS-side boundary rules (ESLint
  `@aether/no-cross-layer-import`). TS layer facades are still stubs;
  revisit when `packages/l5-policy-ts` stops being hand-written.

---

## 2. Current dependency map (as of this wave)

Extracted via `cargo metadata --format-version 1 --no-deps`:

| Crate | Intra-workspace deps |
|---|---|
| `aether-l1-interaction` | `aether-l5-policy` |
| `aether-l2-memory`      | `aether-l5-policy`, `aether-storage` |
| `aether-l3-presence`    | *(none)* |
| `aether-l4-router`      | `aether-l5-policy` |
| `aether-l5-policy`      | `aether-event-bus`, `aether-storage`, `aether-telemetry` |
| `aether-l6-persona`     | `aether-l5-policy` |
| `aether-l7-trust`       | `aether-l5-policy` |
| `aether-event-bus`      | *(none — leaf)* |
| `aether-storage`        | *(none — leaf)* |
| `aether-media-engine`   | *(none — leaf)* |
| `aether-telemetry`      | *(none — leaf)* |

### Doctrine rules against which the map was judged

From `planning/00_VISION_AND_GUARDRAILS.md` §4.1 and `CLAUDE.md` §1.4:

1. L5 is the non-bypassable policy gate. Sibling engines (L1/L2/L3/L4/
   L6/L7) **may** depend on `aether-l5-policy`. L5 **must not** depend
   on any sibling engine.
2. Sibling engines do not import each other. Coordination happens via
   the event bus, shared types, or typed L5 / L6 outputs.
3. Shared-infra crates (`event-bus`, `storage`, `media-engine`,
   `telemetry`) are leaves — depended on, never depending on engines.
4. L5 may depend on shared-infra. (Concretely today: event-bus,
   storage, telemetry.)

### Result

**Zero violations.** Every edge in the map above is doctrine-consistent:
- Five engine → L5 edges (L1, L2, L4, L6, L7) — intentional gate plumbing.
- One engine → shared-infra edge (L2 → storage) — per the L2 memory
  kernel interface pack.
- Three L5 → shared-infra edges — per the Wave 3 system design.

The code did not drift during Waves 0–4 or Wave 3.5. Wave 4.1 converts
that happy state into something a CI job enforces going forward.

---

## 3. Rules implemented

### Tool

`tools/lint-layer-boundaries/check.py` — a ~200-line Python 3.9+
script, standard library only, invoked via `python
tools/lint-layer-boundaries/check.py` from the repo root.

### Allowlist (encoded in `ALLOWED`)

```python
ALLOWED = {
    "aether-l1-interaction": {"aether-l5-policy"},
    "aether-l2-memory":      {"aether-l5-policy", "aether-storage"},
    "aether-l3-presence":    set(),
    "aether-l4-router":      {"aether-l5-policy"},
    "aether-l5-policy":      {"aether-event-bus",
                              "aether-storage",
                              "aether-telemetry"},
    "aether-l6-persona":     {"aether-l5-policy"},
    "aether-l7-trust":       {"aether-l5-policy"},
    "aether-event-bus":      set(),
    "aether-storage":        set(),
    "aether-media-engine":   set(),
    "aether-telemetry":      set(),
}
```

### Algorithm

1. Shell out to `cargo metadata --format-version 1 --no-deps
   --manifest-path <repo>/Cargo.toml`.
2. Parse `workspace_members` to learn the set of workspace crate names.
   Supports both the legacy (`"name version (path+...)"`) and current
   (`"path+file:///...#name@version"`) Cargo formats.
3. For every workspace package in `ALLOWED`, inspect its
   `dependencies` array. Filter to intra-workspace targets only
   (external crates are ignored; `cargo-deny` covers those).
4. For every edge not in the source's allowlist, emit a
   `Violation(source, target, kind, reason)` with a human-readable
   reason string that identifies the specific doctrine rule broken
   (L5 → engine, engine ↔ engine, shared-infra → engine, or generic
   "not in allowlist").
5. Exit `0` on clean, `1` on any violation, `2` on tool error
   (cargo missing, repo root not found).

### Why Python, not `cargo-deny`

`cargo-deny`'s `[bans]` block is excellent at **external-crate** hygiene
— duplicate versions, wildcard pinning, license allowlists, unknown
registries. The existing `deny.toml` already handles that layer and
stays in place.

For **intra-workspace** edges, `cargo-deny`'s `wrappers = [...]`
mechanism can express the rules but requires a `[[bans.deny]]` entry
per crate, and the error messages are phrased for external-crate
context. A ~200-line Python script reads the same `cargo metadata`
output `cargo-deny` does, applies a single ALLOWED table, and emits
doctrine-referenced reasons. No extra install step, no CI build cost.

If the rule surface ever outgrows the script (dozens of crates,
transitive checks, etc.), the script's output is stable enough to swap
for a dedicated Rust binary without changing what contributors run.

### Self-test

The plant-and-revert sanity check was run during this wave:

1. Clean state: `python tools/lint-layer-boundaries/check.py` → exit 0,
   "0 violations."
2. Planted forbidden edge `aether-l3-presence → aether-l5-policy` in
   `packages/l3-presence/Cargo.toml`. Re-ran the linter → exit 1, one
   violation reported with the correct source/target/reason.
3. Reverted the plant. Re-ran → exit 0, clean.

The linter behaves correctly on both passing and failing inputs.

---

## 4. Violations found and how handled

**None.** The allowlist matches current code exactly. No fixes were
needed and no narrow exceptions were carved.

This is the best case: doctrine and code agreed before the enforcer
turned on, so the enforcer ships with zero starting debt. The first
contributor who accidentally tangles a layer will hit the gate
immediately.

---

## 5. Exceptions / escape hatch

No current exceptions.

The process for adding a new allowed edge (documented in
`tools/lint-layer-boundaries/README.md` §"How to propose a new
cross-layer contract"):

1. Open an architecture-proposal issue using the Feature Request
   template.
2. Reference the planning doc the change touches.
3. Wait for a `DECISION_LOCK_PASS_*.md` entry.
4. The code PR then updates the `ALLOWED` table in `check.py` alongside
   the new `[dependencies]` line. Unilateral ALLOWED edits are
   block-the-PR violations.

This keeps the enforcement layer aligned with the doctrine layer by
construction.

---

## 6. How contributors run the lint

### Locally

From the repo root:

```bash
python tools/lint-layer-boundaries/check.py
```

Typical output:

```
layer-boundary check: OK (0 violations)
  checked 11 workspace crates; engines 7, shared infra 4.
```

On violation:

```
layer-boundary violations detected:
  aether-l3-presence -> aether-l5-policy  [dependencies]
      'aether-l3-presence' is not permitted to depend on 'aether-l5-policy'.
      Update the ALLOWED table in tools/lint-layer-boundaries/check.py if
      this edge is doctrinal; otherwise reshape the import to go through
      shared types or the event bus.

1 violation(s). See tools/lint-layer-boundaries/README.md for how to resolve.
```

Machine-readable output for editor integrations / CI log parsing:

```bash
python tools/lint-layer-boundaries/check.py --json
```

### In CI

`.github/workflows/ci.yml` now defines a `layer-boundaries` job that
runs on every push / PR to `dev` or `master`:

```yaml
layer-boundaries:
  name: Layer boundaries (cross-crate dep lint)
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: dtolnay/rust-toolchain@stable
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - run: python tools/lint-layer-boundaries/check.py
```

The job fails the build on any violation. No `continue-on-error` — the
whole point of Wave 4.1 is that these rules block PRs.

---

## 7. Files created / modified

### New

- `tools/lint-layer-boundaries/check.py` — the linter.

### Modified

- `tools/lint-layer-boundaries/README.md` — replaced the Wave 1
  placeholder content with the real how-to (rules table, run
  instructions, failure-interpretation guide, proposal process,
  "why Python" rationale).
- `.github/workflows/ci.yml` — added `layer-boundaries` job between the
  existing `rust` and `typescript` jobs.
- `README.md` — "Next in priority" triage retires Wave 4.1 and notes
  the wave landed 2026-04-19 with a pointer to this report.
- `ROADMAP.md` — "Completed" section records Wave 4.1;
  "Next — in priority order" resequences to L5 durable persistence →
  first-logic slice → community demo slice → public-release polish.

### Not modified

- `tools/lint-layer-boundaries/deny.toml` — kept as-is. Its external-
  crate hygiene (`multiple-versions`, `wildcards`, `licenses`,
  `sources`) is still the right use of `cargo-deny`. The
  intra-workspace `[bans]` comment block is now documented as covered
  by `check.py` instead, but left in `deny.toml` as reference.
- Any `packages/*/Cargo.toml` — no violations required fixing.
- Any engine or shared-infra code — Wave 4.1 is governance, not logic.

---

## 8. Effect on contributor safety and drift risk

### Before Wave 4.1

- Boundary rules lived in `planning/00_VISION_AND_GUARDRAILS.md`,
  `CLAUDE.md`, and scattered Wave-report asides.
- A contributor adding `aether-l2-memory = { path = "..." }` to
  `packages/l5-policy/Cargo.toml` would compile, test, and merge
  cleanly; the drift would only be caught in architecture review.
- Review load grew linearly with PR volume.

### After Wave 4.1

- The ALLOWED table in `check.py` is the machine-readable encoding of
  the doctrine. CI fails fast on any forbidden edge.
- Adding a new allowed edge requires updating both the code and the
  ALLOWED table in the same PR, forcing reviewers to see the intent
  change explicitly.
- Contributors run `python tools/lint-layer-boundaries/check.py`
  locally in ~200 ms before pushing — shorter feedback loop than
  waiting on CI.
- Architecture-drift risk drops from "caught by reviewer attention"
  to "caught by CI before review."

### Remaining risks (future waves)

1. The linter only checks `[dependencies]` and `[dev-dependencies]` in
   Cargo.toml. It does not parse `use` statements, so a hypothetical
   `pub use` re-export across a shared crate could still leak an
   engine type into another engine. Mitigation: prefer small, typed
   shared crates; keep eyes on `packages/types` growth.
2. The linter doesn't enforce the "L5 is single writer for side
   effects" rule — that is `tools/lint-policy-bypass/`'s job in a
   later wave.
3. The linter doesn't check TypeScript packages. When
   `packages/l5-policy-ts` becomes generated, the TS side will want a
   paired ESLint rule.

These are enumerated rather than assumed-away; none is a Wave 4.1
regression.

---

## 9. Recommendation: ship the CI wiring now

**Yes, keep the `layer-boundaries` CI job active.** The local
self-test showed the tool behaves correctly on both clean and dirty
input. There are zero current violations, so activation carries no
risk of blocking unrelated PRs. And there is active contributor
traffic expected once the preview tag is pushed, which is exactly
when the gate is most valuable.

If a future contributor hits the gate on a legitimate architecture
change, the `README.md` §"How to propose a new cross-layer contract"
process is documented and takes one issue → one decision-lock → one
PR to execute.

---

## 10. Recommended next session

**L5 durable persistence.** Scope (per `ROADMAP.md` §"Next"):

- `SqliteGrantLedger` + `SqliteAuditStore` behind the existing
  ledger / audit traits in `packages/l5-policy/src/storage_hooks.rs`.
- `Store` trait abstraction over the driver choice in
  `packages/storage/`.
- Migration `0002_audit_chain.sql` with hash-chain + HMAC triggers.
- Feature flag `durable-persistence` on `aether-l5-policy`; flip
  default once the end-to-end "write grant → tear down → reopen →
  grant still there" integration test passes.
- `WAVE*_EXECUTION_REPORT_YYYY-MM-DD.md` alongside.

This wave will add a new allowed edge (L5 → storage already exists,
so no ALLOWED changes needed). The Wave 4.1 linter will validate
that change.
