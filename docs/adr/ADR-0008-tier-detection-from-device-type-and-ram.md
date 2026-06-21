# ADR-0008: Tier detection from device_type + system RAM (replaces wgpu max_buffer_size signal)

- **Status:** **Accepted** (Don ratified 2026-04-24 mid-autonomous-run; implementation landed in same wrap batch).
- **Date:** 2026-04-24
- **Deciders:** Don (owner). Claude proposes, captures rationale from on-hardware validation data.
- **Supersedes:** ADR-0006 §Decision 2 (the `max_buffer_size`-based VRAM estimate path) and §Decision 3 (the recommendation rule that consumed it).
- **Superseded by:** nothing yet. A future ADR may add NVML/IOKit feature-gated probes for real VRAM (held per ADR-0006 §Open items).
- **Related:** `docs/adr/ADR-0006-hardware-tier-model.md` (the foundational tier model, which this ADR refines), `planning/validation_2026-04-24/VALIDATION_REPORT.md` §4 (the on-hardware data that motivates the change).

## Context

ADR-0006 §Decision 2 specifies hardware detection via `wgpu::Instance::enumerate_adapters` + `Limits::max_buffer_size` as a "conservative *lower bound*" for VRAM. The Session A implementation in `apps/desktop/src-tauri/src/hardware.rs` and the recommendation rule in `apps/desktop/src-tauri/src/tier.rs` consume this estimate as `vram_gb_estimate = max_buffer_size / 1 GB` and apply a 50% rule to reach effective_vram, then compare against per-tier floors.

On 2026-04-24, the autonomous validation run executed the inspection on Don's RTX 3090 Ti (24 GB physical VRAM). Three different wgpu backends reported wildly different `max_buffer_size`:

| Backend | `max_buffer_size` reported | `vram_gb_estimate` | Tier impact |
| --- | --- | --- | --- |
| Vulkan | `18446744073709551615` (= u64::MAX, sentinel for "unlimited") | `4,294,967,295` (≈ 4 billion GB) | Forge (by accident — sentinel happens to be > 24) |
| DX12 | `2147483647` (= 2^31-1, signed-int max — DX12 driver default cap) | `1` GB | Spark |
| GL | `2147483647` | `1` GB | Spark |

The current adapter-priority rule (`device_type` priority + `vram_gb_estimate` as tiebreaker) picks Vulkan because the sentinel makes it score highest. A 24 GB workstation card therefore gets classified Forge — but **only because the sentinel happened to be > 24**. On a system where the priority logic resolves DX12 first (different wgpu version, different driver, headless context), the same hardware would be classified Spark.

The heuristic is therefore not measuring VRAM. It is measuring "did the driver expose a sentinel." Lesson 1 from the Session A handoff (`HANDOFF_2026-04-24_M2_RUN_3_SESSION_A_COMPLETE.md` §7) anticipated this: `wgpu::Limits::max_buffer_size` is a single-allocation ceiling, not total VRAM. The validation data confirms the lesson is now an active correctness bug, not a future risk.

ADR-0006 §Open items already flagged NVML/IOKit refinements as future work. This ADR is the *interim* fix to make tier classification reliable on real hardware without waiting for the platform-specific probes.

## Decisions

### 1. Drop `max_buffer_size` from the recommendation rule entirely.

The rule will no longer read `gpu.vram_gb_estimate`. It will continue to be **populated** in `HardwareSnapshot` (it's diagnostic information that's worth surfacing in Settings UI for the curious user, and it's already serialised into `tier.json`), but it ceases to be a *decision* input.

### 2. New rule: `device_type` + `total_ram_gb`.

```rust
pub fn recommend_tier(snapshot: &HardwareSnapshot) -> Tier {
    let Some(gpu) = snapshot.gpu.as_ref() else {
        return Tier::Spark;
    };
    let is_discrete = matches!(gpu.kind, GpuKind::DiscreteGpu | GpuKind::VirtualGpu);
    if !is_discrete {
        return Tier::Spark;
    }
    // 50% headroom rule applied at recommendation time per ADR-0006 §Constraint 2.
    let effective_ram = snapshot.total_ram_gb / 2;
    if effective_ram >= 16 { Tier::Forge }       // total RAM >= 32 GB → workstation
    else if effective_ram >= 8 { Tier::Flame }   // total RAM >= 16 GB → enthusiast
    else { Tier::Spark }                         // <16 GB total → Spark
}
```

**Rationale.** `sysinfo::System::total_memory` returns reliable RAM figures across every platform we care about. Workstation-class systems (the realistic Forge audience) have ≥32 GB RAM. Enthusiast/creator desktops (the Flame audience) have ≥16 GB. Sub-16-GB systems are realistically Spark territory regardless of GPU. The 50% headroom rule (ADR-0006 §Constraint 2) still applies: we recommend the tier whose envelope fits in *half* of detected resources.

We give up one classification: the ADR-0006-test-named "discrete with low VRAM falls back to Spark" case (current `discrete_with_low_vram_falls_back_to_spark`). A 4 GB discrete card with 16 GB RAM would now be classified Flame instead of Spark. This is an acceptable trade — small discrete cards (GTX 1050-class) are increasingly rare, and the user-override surface (ADR-0006 §Decision 4) covers the case where the user wants a more conservative tier on weak discrete hardware.

### 3. `max_buffer_size` becomes diagnostic-only.

Continue to populate `GpuInfo.vram_gb_estimate` so it shows up in the Settings UI and `tier.json::hardware_snapshot`. Add an inline comment + ADR cross-reference noting it is unreliable cross-backend and not a decision input.

Rename to `vram_gb_diagnostic` in a future ergonomic commit if desired; not required for correctness. Field-rename would be a wire-shape change requiring TS regen — held as a separate, optional follow-up.

### 4. Multi-adapter selection unchanged.

The "highest-priority adapter wins" rule (`detect_best_gpu` in hardware.rs) remains in force. Discrete > integrated > virtual > cpu > other. The tiebreaker on equal priority becomes a no-op (since `vram_gb_estimate` is no longer a decision input — but kept as a stable ordering for diagnostic purposes).

### 5. Unit-test updates.

The existing tests in `tier.rs::tests` need updating:
- `discrete_with_high_vram_and_high_ram_recommends_forge` — replace assertion to use `total_ram_gb`-based classification.
- `discrete_with_mid_vram_recommends_flame` — same.
- `discrete_with_too_little_ram_falls_back_to_spark` — preserved (low RAM still → Spark).
- `discrete_with_low_vram_falls_back_to_spark` — **delete or invert.** Under the new rule, low-VRAM-discrete + high-RAM is no longer Spark.

A new test `discrete_with_high_ram_and_unreliable_vram_estimate_picks_forge` should be added, seeding the snapshot with `vram_gb_estimate = u32::MAX` (mimicking the Vulkan sentinel) to prove the rule no longer depends on that field.

### 6. ADR-0006 cross-reference.

ADR-0006 §Decision 2 and §Decision 3 should be marked "see ADR-0008 for tier-recommendation rule." Don can decide whether to inline a "Superseded by ADR-0008" header on those sub-decisions or leave the cross-reference as-is.

## Alternatives considered

### Add NVML / IOKit feature gates immediately.

Would give us actual VRAM for NVIDIA/Apple hardware. Rejected for now: vendor-specific FFI is a real ~200 LOC investment, requires per-platform test coverage, and is a separate concern from "fix the broken default." Held for follow-up ADR per ADR-0006 §Open items.

### Try every backend's `max_buffer_size` and pick the median.

Would reduce single-backend sentinel sensitivity. Rejected: still measures the wrong thing (allocation ceilings, not VRAM), and the cross-backend variance (4 billion GB vs 1 GB) is so wide that no central-tendency stat saves us.

### Hard-code per-vendor VRAM tables (NVIDIA RTX 3090 Ti = 24 GB, etc.).

Brittle, maintenance-heavy, won't cover new hardware. Rejected.

### Defer the fix entirely; rely on user manual override.

User override exists per ADR-0006 §Decision 4. But the *recommendation* is the whole point of auto-detection; if the recommendation is wrong, every new install picks the wrong tier and only power users know to override. Rejected.

## Consequences

**Positive.**

- Tier auto-detection becomes deterministic across drivers / wgpu versions / backends.
- Removes the most likely source of "Aether picked the wrong tier on my machine" reports.
- Aligns the implementation with what the field name `total_ram_gb` already implies should be the primary RAM signal.
- Sets up cleanly for the future NVML/IOKit refinement: those probes can populate a separate `vram_gb_actual: Option<u32>` field that consuming ADRs can opt into without re-doing the broken `max_buffer_size` plumbing.

**Negative.**

- One existing test inverts; one or two new tests need adding.
- A small-discrete-GPU edge case loses its Spark classification (needs user override to recover). Real-world frequency: rare in 2026.
- The Spark/Flame/Forge tier names lose their direct relationship to "VRAM-based" naming intuitions some readers might have. The names were always meant to be hardware-envelope identities, not "small/medium/large VRAM" — but this fix makes the disconnect explicit.

**Neutral.**

- ADR-0006 stays in force; this ADR refines two of its decisions. No other ADRs need to change.

## Open items (NOT decided here)

- Whether to rename `vram_gb_estimate` → `vram_gb_diagnostic` (wire-shape change, separate decision).
- NVML / IOKit feature gates for real VRAM (held per ADR-0006 §Open items).
- Whether the Settings UI should surface a "you can override your detected tier" hint when the user's GPU has more RAM than the recommendation implies (UX call, not architecture).

## Implementation note

This ADR is **Proposed**, not Accepted. Implementation is held until Don ratifies. If accepted, the change set is:

1. `tier.rs::recommend_tier` rewrite per Decision 2.
2. `tier.rs::tests` updates per Decision 5.
3. ADR-0006 inline cross-reference update per Decision 6.
4. (Optional) field rename per Decision 3.

Estimated ~30-60 LOC change in `tier.rs`; one focused commit.

---

(end of ADR-0008)
