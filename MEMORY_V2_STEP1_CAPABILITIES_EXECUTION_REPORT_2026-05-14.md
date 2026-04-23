# Memory V2 Step 1 — additive L5 capabilities — execution report (2026-05-14)

**Status:** Shipped locally on `dev` (commits `f762032`, `b2b7963`). Push not authorized.

## Goal

Land the first Memory V2 code slice — L5-first additive capability
variants per `docs/MEMORY-V2-ARCHITECTURE.md` §10 item 1. No L2
consumers yet; policy surface, write/read plumbing, Memory tab,
and rot guard are later steps.

## Surfaces touched

### `packages/l5-policy/src/capability.rs`

Three new `Capability` variants appended to the `Memory` group:

- `Capability::MemoryWrite`  — coarse "write any memory item"
- `Capability::MemoryForget` — per-item forget, distinct from the
                               pre-V2 bulk `MemoryDelete`
- `Capability::MemoryEdit`   — mutate an existing memory item

`MemoryRead` already existed and fills the fourth slot the design
doc calls for. The older finer-grained variants
(`MemoryWriteSession`, `MemoryWriteDurable`, `MemoryWriteExtractedPref`,
`MemoryUseInFutureTask`, `MemoryExport`, `MemoryDelete`) stay —
additive-only, no renames, no removals.

### `packages/l5-policy/src/engine.rs`

- `default_risk_for`: Read → Low; Write / Edit / Forget → Medium.
  Bulk `MemoryDelete` keeps its pre-V2 higher posture.
- Four new L5-first tests:
  - `memory_v2_coarse_capabilities_exist_and_hash` — Hash/Eq
    round-trip so step 2's policy maps can key by these variants.
  - `memory_v2_capabilities_have_sensible_default_risks`.
  - `memory_v2_capabilities_have_no_preset_default_yet` — locks
    the "L5-first, no preset yet" semantics; flipping this test
    is the conscious step-2 trigger.
  - `memory_v2_capabilities_round_trip_through_serde`.

### `packages/l7-trust/src/approval.rs`

- `human_capability` match filled in with the three new variants
  (`memory.write`, `memory.forget`, `memory.edit`). Match stays
  exhaustive so any future L5 addition trips a compile error in
  L7 first — intended enforcement seam.

## Checks — all green

- `cargo test -p aether-l5-policy` — **16 / 16** (was 12; +4)
- `cargo test --workspace` — 137 / 137
- L4-router, shell, vision / voice rot guards, TS matrix — all
  unchanged by this slice and all passing.

## Hard-constraint compliance

- **No push.** ✅
- **No `AuditRecordEvent` shape change.** ✅ Additive variants
  only; the event struct still carries `capability: Capability`
  and the new values flow through serde transparently.
- **No preset defaults yet.** ✅ Any turn that requests
  `MemoryWrite`/`Edit`/`Forget` today resolves to
  `NeedsUpgrade` — exactly the L5-first semantic.
- **No L2 consumers.** ✅ Memory V2 step 2 is where the write/
  read plumbing wires these capabilities into the memory kernel.

## Design decisions worth noting

1. **Two layers of Memory capabilities coexist.** The older
   session/durable/extracted-pref split is preserved; Memory V2
   adds a coarser surface on top. Step 2 will decide which layer
   the Ask flow keys on for user-sensitive domains (likely the
   coarse one, with the granular ones becoming internal book-
   keeping).
2. **Per-item `MemoryForget` is distinct from bulk `MemoryDelete`.**
   The doc's §1 flow separates user-initiated forget from
   retention-sweep TTL expiry from bulk delete. Keeping three
   variants keeps the audit log's intent-distinguishable.
3. **`MemoryEdit` at Medium risk.** Edit is mutation; we don't
   want Auto approval on user-sensitive domains. Step 2's policy
   surface sets the per-domain Ask default.

## What is deliberately NOT in this slice

- `memory.json` policy surface (step 2).
- Per-domain Ask wiring (step 2).
- L2 write/read plumbing (step 3).
- Memory tab in Trust drawer (step 4).
- Retention sweep (step 5).
- Embeddings (step 6).
- Rot guard (step 7).

## Next step

Memory V2 step 2 — `memory.json` config surface +
`MemoryPolicyRegistry` + Settings section + Tauri commands for
policy read/write. Landing sequence mirrors
`presence_config.rs`'s additive-default-safe contract.
