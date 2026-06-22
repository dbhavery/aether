# ADR-0001: MemoryDomain enum reconciliation

- **Status:** Accepted
- **Date:** 2026-04-23
- **Deciders:** Don (owner).
- **Supersedes:** nothing.
- **Superseded by:** nothing.

## Context

`packages/l2-memory/src/kernel.rs` declared a `MemoryDomain` enum
with the variants `Personal / Work / Health / Finance / Creative /
System` as a Wave 4 planning stub. Separately,
`apps/desktop/src-tauri/src/memory_config.rs` declared a
`MemoryDomain` enum with the variants `Session / Durable / Facts /
Projects / Preferences / Artifacts` — the six-domain taxonomy
`docs/MEMORY-V2-ARCHITECTURE.md` §1 freezes as authoritative.
Two enums with the same name, different variants, in the same
workspace.

Memory V2 steps 1–4 shipped against the shell enum exclusively.
`memory_config.rs`, `memory_service.rs`, the Tauri command
surface, the TS bindings, and the new Trust-drawer Memory tab
all speak the shell enum. A grep across the workspace confirms
the kernel surface has **zero real-world consumers**:

| Symbol | External consumers |
| --- | --- |
| `kernel::MemoryKernel` trait | 0 |
| `kernel::MemoryItem` struct | 0 |
| `kernel::MemoryDomain` enum | 0 |
| `kernel::PrivacyClass` | 0 |
| `kernel::RetentionKind` | 0 |
| `kernel::EmbeddingStore` trait | 0 |
| `kernel::EmbeddingRef` | 0 |

`packages/l2-memory/src/lib.rs` itself carries `#![allow(dead_code)]`
and the header comment calls the crate a "Wave 4 stub".

Memory V2 step 5 (retention sweep) is the first subsystem work
that cannot ignore the mismatch: the sweep must know which
domain owns a row to apply per-domain retention from
`memory.json`. Picking the wrong reconciliation path would
invalidate most of step 5's work.

## Decision

For Memory V2 Wave 1 and beyond, **we retire the L2 kernel stub**
(`packages/l2-memory/src/kernel.rs`) and treat the shell's
six-domain taxonomy as the single source of truth.

Concretely:

1. **`MemoryDomain` relocates from the shell to L2.**
   `apps/desktop/src-tauri/src/memory_config.rs::MemoryDomain`
   moves to a new module `packages/l2-memory/src/domain.rs`. The
   shell imports it from `aether_l2_memory::MemoryDomain`
   thereafter. This gives the enum a shared home without
   coupling a future background-sweep job to the desktop binary.

2. **`kernel.rs` is deleted.** The `MemoryKernel` trait,
   `MemoryItem` struct, kernel-side `MemoryDomain`, `PrivacyClass`,
   `RetentionKind`, `EmbeddingStore` trait, `EmbeddingRef` all go.
   Re-exports in `lib.rs` are trimmed accordingly.

3. **`MemoryRisk` stays in shell `memory_config.rs`.** It is
   policy configuration (per-domain Ask / Auto / Deny), not the
   taxonomy itself, and its scope is the shell's policy surface.

4. **The `SessionMemoryStore` contract (and any future
   domain-typed durable store) become the only shared boundary
   between layers.** Background jobs — retention sweep
   (step 5), embeddings worker (step 6) — speak the L2-hosted
   `MemoryDomain` via store method signatures, not via a separate
   kernel trait.

## Rationale

- **Dead code is a liability.** Keeping a parallel kernel
  taxonomy alive implies there's a design we're protecting. In
  fact, the real design shipped as the shell enum + the session
  store, and everything real has already migrated there. The
  kernel stub was authored before the Memory V2 doc locked the
  six domains.
- **Option 1 (refactor kernel enum to match shell) does
  speculative work on dead code.** It keeps the kernel trait
  alive "just in case" while no consumer wants it.
- **Option 2 (keep both + mapper) permanently taxes every
  Memory call** with no forcing function. Classic
  over-engineering: two vocabularies for one concept.
- **Option 3 (this decision) matches what steps 1–4 actually
  did.** The shell enum is the design-doc enum; the storage
  API is the real boundary; future background jobs need the
  enum in L2, not in a desktop-only module.

## Consequences

### Immediate (Memory V2 step 5 — "Memory Sweep" session)

- New file: `packages/l2-memory/src/domain.rs` exports
  `MemoryDomain` (copy of the shell variants verbatim,
  including `const ALL` and `label()`), plus documentation
  tying it to `docs/MEMORY-V2-ARCHITECTURE.md` §1.
- `packages/l2-memory/src/lib.rs` re-exports
  `domain::MemoryDomain` and drops the kernel re-exports.
- `packages/l2-memory/src/kernel.rs` is deleted.
- `apps/desktop/src-tauri/src/memory_config.rs` imports
  `MemoryDomain` from `aether_l2_memory` and removes its local
  declaration.
- The retention sweep operates through SessionMemoryStore +
  `MemoryConfig::retention_for(domain)`.

### Downstream (steps 6 + 7)

- Memory V2 step 6 (embeddings) gets a fresh `EmbeddingStore`
  trait in `packages/l2-memory/src/embeddings.rs` when that
  work starts, NOT from kernel.rs. The previous
  `EmbeddingStore` / `EmbeddingRef` surface is design stub
  with zero consumers and no need to preserve.
- Memory V2 step 7 (rot guard) anchors its manifest against
  the new `packages/l2-memory/src/domain.rs` file, not kernel.rs.

### Out of scope

- `MemoryRole`, `TurnMemoryRecord`, `SessionMemoryStore`,
  `RecentMemoryWindow`, `RecentMemoryConfig`, `DurableSessionStore`,
  `SqliteSessionMemoryStore`, `RetentionPolicy` all stay
  unchanged. Every in-use symbol in `packages/l2-memory/` is
  unaffected.
- `MemoryRisk` stays in the shell. This ADR does not move it.
- No changes to `AuditRecordEvent`, the Capability enum, or
  the L5 policy engine.

## Alternatives considered and rejected

- **Option 1 — Replace L2 kernel enum with the shell enum, keep
  the kernel module.** Rejected: refactors a file with zero
  consumers into a different shape of unused code. Work without
  an immediate beneficiary.
- **Option 2 — Keep both enums, add a mapping layer.** Rejected:
  creates a permanent two-vocabulary tax for no forcing function.
  Future domain additions would require touching both enums and
  a mapper; bugs in the mapper would silently desync. The cost
  is ongoing; the benefit is hypothetical flexibility nobody has
  asked for.

## Follow-ups

- Memory V2 step 5 implementation (next session, "Memory Sweep").
- Any future Memory-domain change extends this ADR or opens
  a new one. The six-domain taxonomy is deliberately frozen;
  adding a seventh domain is an architecture-level decision.
