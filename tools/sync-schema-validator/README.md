# sync-schema-validator

Synthetic event-stream validator for the T2.1 mobile sync schema's
conflict-resolution rules.

**Scope:** pure-Python, no GPU, no new packages, no Cargo workspace changes.
This is a `tools/` scaffold (governance / codegen tier per CLAUDE.md §4),
not a `packages/*` crate.

**What it does:** runs a fixture suite of synthetic two-device event
streams through the conflict-resolution rules in
`docs/adr/ADR-0016-mobile-sync-schema.md` and asserts the
expected convergence outcome on every scenario in its test matrix.

**Why it exists:** doctrine §8 — self-test before Don review. Any
change to a conflict-resolution rule must run this validator green
before reaching Don.

## Run

```
python tools/sync-schema-validator/validate.py
```

Exit code 0 = all scenarios pass. Non-zero = at least one mismatch.

## Layout

- `validate.py` — entry point + scenarios + assertions.
- `engine.py` — pure-functional rule implementations
  (`resolve_memory_item`, `resolve_grant`, `merge_cost_counters`,
  `resolve_approval`, `merge_persona_pointer`).

No external dependencies. Standard library only.

## When to extend

- New conflict-resolution rule introduced in §4 → add an `engine.py`
  function and a `validate.py` scenario.
- New domain added to sync (e.g. a 7th MemoryDomain) → no change here;
  rules are domain-agnostic.
- Schema-version bump → add a scenario covering the version-mismatch
  reject path.

## Limitations

This validator does NOT:
- Exercise real SQLite or any storage layer.
- Test the audit-chain HMAC merge protocol (that's a future test
  harness once the merge code exists).
- Test the transport (mDNS, WebSocket) — that's an integration concern.

It exercises **the rules**, not the implementation. If the rules are
right and the implementation faithfully implements them, the system
converges. The implementation is a separate test surface.
