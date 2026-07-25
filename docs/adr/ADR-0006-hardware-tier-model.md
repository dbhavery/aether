# ADR-0006: Hardware tier model — Spark / Flame / Forge

- **Status:** Accepted (Don, 2026-04-24, with external reviewer concurrence on the Run 3 discuss-session output).
- **Date:** 2026-04-24
- **Deciders:** Don (owner). Claude captures the design + rationale from the Run 3 discuss session.
- **Supersedes:** nothing (first ADR to formalise the tier concept).
- **Superseded by:** nothing.
- **Related:** `docs/adr/ADR-0003-model-defaults-supersession.md` (gemma4:e4b + bge-m3 pin — becomes *tier-parameterised* under this ADR), `docs/adr/ADR-0007-embeddings-onboarding.md` (consumes tier). Future: ADR-0008 for avatar medium (reserves into the VRAM budgets this ADR sets).

## Context

Aether is a personal, local-first AI companion. Its end-state capability surface spans LLM inference, embedding inference, TTS, local vision, and a bespoke real-time avatar (to be built; ADR-0008). That stack's compute footprint varies by an order of magnitude depending on whether Aether is running on an integrated GPU or a flagship discrete card.

The design constraint set from the Run 3 discuss session:

1. **Quality bar is constant across hardware.** Avatar must be indistinguishable from a real human at every tier. Text + voice + memory must feel human at every tier. Tiers vary the *medium* (Tier Low: real recorded video; Tier Mid/High: neural rendering) but not the quality bar.
2. **Never bog the user's hardware.** Aether targets ≤50% of available GPU VRAM as the *recommended floor* for tier auto-selection, leaving headroom for games, other AI work, browser workloads, background apps. Aether does not cap itself at runtime — users who dedicate their hardware to Aether may safely allocate well above 50%, and Aether uses what is available.
3. **Quality posture: optimise for quality, not for footprint.** Where a knob exists that trades quality for resource efficiency (truncated context, partial GPU offload, aggressive model eviction, silent tier downgrade under contention), the default position is the quality-preserving setting. Resource pressure is *surfaced* to the user (per ADR-0007's best-effort + warning posture); it is never absorbed silently by quietly degrading model fidelity. Future ADRs (TTS, vision, avatar) inherit this posture by default.
4. **Three tiers.** One tier is too coarse; more than three is fragmentation. Three covers integrated / mid-range discrete / flagship discrete, which maps cleanly onto the consumer GPU market.
5. **Hardware auto-detection.** The installer / first-run flow detects the machine and recommends a tier. User can override (choose a lower tier for headroom; pick Low manually if they want minimum footprint).
6. **Retail SaaS integrations are out of scope.** Avatar and supporting capabilities are metal-up Rust builds using `wgpu` + ML-in-Rust (candle/burn-family). Tier budgets reserve VRAM for those future systems without committing to specific stacks here.

This ADR defines the tier model itself. It does **not** enumerate which specific models / avatar stacks run at each tier — that's deliberately deferred to the consuming ADRs (ADR-0007 for embeddings, ADR-0008 for avatar, future ADRs for TTS / vision / LLM) so they can evolve independently on top of a stable tier contract.

## Decisions

### 1. Three named tiers: Spark / Flame / Forge.

Provisional names, chosen to match Aether's existing "warmth / fire" semantic palette and to avoid numeric tiers that imply "better / worse" rather than "different envelopes."

| Tier | Target hardware envelope | VRAM headroom (50% rule) | Rough user identity |
| --- | --- | --- | --- |
| **Spark** | Integrated GPU or CPU-only. Typical 0 – 8 GB dedicated VRAM, 16 GB system RAM. | Effective budget: 0 – 4 GB VRAM, ~4 GB system RAM. | Laptops, ultrabooks, older desktops. Aether runs correctly, with the avatar medium chosen to not require real-time neural inference. |
| **Flame** | Mid-range discrete GPU. Typical 12 – 16 GB VRAM total (RTX 4070, RX 7800 XT, M2 Pro/Max). | Effective budget: 6 – 8 GB VRAM, ~8 GB system RAM. | Enthusiast / creator desktop. All standard features on, neural avatar path viable. |
| **Forge** | High-end discrete GPU. 24+ GB VRAM total (RTX 4090, RTX 5090, M3 Ultra, workstation cards). | Effective budget: 12+ GB VRAM, ~16 GB system RAM. | Flagship machine. Every capability on, largest viable models, full-fidelity avatar. |

Note on Apple Silicon: unified memory means the "VRAM" concept maps to a portion of system RAM. Detection treats the unified pool as both, with the 50% rule applied against total unified memory.

### 2. Auto-detection via `wgpu` + `sysinfo` + `fs::available_space`. No new platform-specific dependencies.

Detection runs once at first launch and again when the user clicks "Re-detect hardware" in Settings. Reads:

- **GPU adapter list** via `wgpu::Instance::enumerate_adapters`. For each adapter: `AdapterInfo::{vendor, device, device_type}`, `Limits::{max_texture_dimension_2d, max_buffer_size}`, backend (Vulkan, Metal, DX12, etc.).
- **GPU VRAM estimate.** `wgpu` does not expose VRAM directly on all backends; we use the `max_buffer_size` limit as a conservative lower bound, supplemented by NVIDIA's `NVML` when feature-gated on Windows/Linux NVIDIA (optional), Apple `IOKit` on macOS (optional). If all advanced probes fail, fall back to `max_buffer_size / 2` as a floor.
- **System RAM / core count** via `sysinfo::System::total_memory`, `cpus()`.
- **Disk available** via `std::fs::available_space` on the app data directory.
- **Ollama GPU status** via `GET /api/ps` — tells us whether any Ollama model is currently loaded on GPU, which validates the GPU path is actually wired end-to-end.

**Default adapter selection on multi-GPU systems:** highest-VRAM discrete adapter wins, with `device_type = DiscreteGpu` preferred over integrated. Multi-GPU disambiguation (laptop with iGPU + dGPU, eGPU enclosures, NVLink pairs) and remote-desktop / headless contexts remain intentionally unresolved here; the user-override path covers the cases where automatic selection picks wrong, and a future detection refinement ADR can revisit when real-world reports warrant.

Cross-platform. No new crates beyond `wgpu` (already indirectly depended on through Tauri / any future rendering) and `sysinfo` (lightweight).

### 3. Recommendation rule. Highest tier whose minimum hardware envelope the detected machine meets or exceeds.

> **2026-04-24 update:** On-hardware validation revealed that `wgpu::Limits::max_buffer_size` is fundamentally unreliable cross-backend (Vulkan reports `u64::MAX` sentinel on 24 GB cards; DX12 reports 1 GB on the same card). The pseudocode below was the original Session A implementation; **see ADR-0008 (Proposed) for the corrected recommendation rule that uses `device_type` + `total_ram_gb` instead of the broken VRAM estimate.** The pseudocode is preserved here as historical context for the original design intent.

Pseudocode:

```
fn recommend_tier(h: DetectedHardware) -> Tier {
    let effective_vram_gb = h.total_vram_gb * 0.5;
    let effective_ram_gb = h.total_ram_gb * 0.5; // unified-memory adjusted

    if effective_vram_gb >= 12.0 && effective_ram_gb >= 16.0 {
        Tier::Forge
    } else if effective_vram_gb >= 6.0 && effective_ram_gb >= 8.0 {
        Tier::Flame
    } else {
        Tier::Spark
    }
}
```

Always recommends the highest-viable tier. Tier caps are set so the "recommended tier fits in 50% of available resources" invariant holds by construction.

### 4. User-override policy. All three tiers always pickable. Unsupported tiers show a clear warning but are not forbidden.

Users can always downgrade (for headroom, battery, shared machine). Attempting to upgrade *past* the recommended tier shows:

> Your hardware is below the recommended envelope for **Forge**. Aether may run slowly, thermal-throttle, or degrade under load. Recommended tier: **Flame**. Proceed anyway? [Cancel] [Use Forge anyway]

No hard-block — the user is adult, their machine, their call. The warning ensures they're informed. Some users deliberately run above spec on fast I/O machines or where their normal use case has low concurrent load.

### 5. Tier-change UX. Settings drawer surface; triggers re-evaluation of downstream manifests.

Changing tier:

1. Updates `tier.json` (new, sibling to `memory.json`).
2. Fires a `tier_changed` event. Any subsystem that reads the tier (embeddings onboarding per ADR-0007; future avatar, TTS, vision, LLM ADRs) re-reads it and updates its own onboarding state — which may mean a new model needs pulling, a running model needs unloading, or a background process needs stopping / starting.
3. Requires an explicit user "Apply tier" step for changes that would trigger large downloads (>500 MB). Preserves the Block-4 / Block-5 rule: *user* triggers infra work, app shows the cost.

Downgrade path must unload models that exceed the new tier's budget. This is handled by the consuming ADRs, not here — ADR-0006 only defines that the tier changed.

### 6. Reserved VRAM budget per tier for future avatar (ADR-0008).

Provisional reservation so ADR-0008 inherits a stable envelope:

| Tier | Reserved for avatar | Remaining budget for LLM + embedding + TTS + vision |
| --- | --- | --- |
| **Spark** | ~0 GB (avatar medium is real recorded video — no neural runtime) | Full effective budget |
| **Flame** | ~4 GB reserved (future neural face model) | Effective budget – 4 GB |
| **Forge** | ~8 GB reserved (future full-fidelity neural face + expressions + gaze) | Effective budget – 8 GB |

These reservations are envelope placeholders, not implementation commitments; consuming ADRs must treat them as soft ceilings pending ADR-0008. The numbers themselves are provisional — ADR-0008 finalises them against the actual Rust avatar stack once that's scoped. Until then, consuming ADRs (ADR-0007 in particular) size their own budgets so they fit within `effective_budget - reserved`.

#### Operational tunable: `OLLAMA_MAX_LOADED_MODELS` (added 2026-04-25)

The numerical reservations above survive intact, but on-hardware validation surfaced a second axis of pressure that is not VRAM-shaped. **`OLLAMA_MAX_LOADED_MODELS` is a first-class tier-tunable for Forge.** Stock Ollama default is 3 concurrent models — once a 4th model loads, Ollama evicts the LRU regardless of how much VRAM is free. On a 24 GB Forge card running the Aether baseline trio (`gemma4:e4b` + `bge-m3` + `nomic-embed-text`, ~17 GB resident), the remaining ~7 GB of headroom is *stranded* under stock config: Ollama caps the slot count, not the byte budget.

**Forge recommended value: `OLLAMA_MAX_LOADED_MODELS=4`** — preserves the baseline trio and reserves one warm slot for the future avatar (ADR-0008) without forcing eviction churn between the trio and the avatar runtime. Spark/Flame keep the stock default of 3 (their VRAM budgets bind first; the slot cap is non-binding on those tiers).

Empirical evidence: Phase 3C 2026-04-25 — loading `qwen3:1.7b` as a 4th model (1.36 GB on disk) evicted `gemma4:e4b` at step 4 despite ~7.8 GB free VRAM at the eviction moment. The avatar slot reservation cross-references ADR-0008, which finalises the avatar's VRAM and slot footprint against the actual Rust stack.

### 7. Storage. `tier.json` sibling to `memory.json`, same contract.

- Serde additive, default-safe on read, unknown fields silently ignored, unknown fields dropped on rewrite.
- Atomic write (temp + rename).
- Malformed JSON → default + WARN, same as other config files.
- Lives beside the other app-data JSON files so all user-owned config is in one place.

Shape:

```json
{
  "selected_tier": "flame",
  "detected_tier": "flame",
  "detected_at_ms": 1713999999000,
  "manual_override": false,
  "hardware_snapshot": {
    "total_vram_gb": 16,
    "total_ram_gb": 32,
    "gpu_vendor": "nvidia",
    "gpu_device": "RTX 4070 Ti",
    "cpu_cores": 16,
    "ollama_gpu_loaded": true
  }
}
```

`detected_tier` tracks the auto-recommendation at last detection. `selected_tier` is the active choice. When they diverge, the Settings UI shows the "your hardware suggests X" hint.

## Alternatives considered

### Single universal Aether (no tiers).

Simplest. Can't coexist with the constant quality bar — either Aether doesn't run on integrated GPUs at all, or the avatar medium on high-end hardware is pegged to what low-end hardware supports. Both are bad. Tiers are the compromise.

### Five tiers (e.g., + laptop-discrete + workstation-server).

More granular, but fragmentation tax: every consuming ADR has to define behaviour at five levels, QA matrix explodes, upgrade paths multiply. Three is enough to cover the meaningful envelopes in the consumer GPU market.

### Hard-floor at Flame-minimum (no Spark tier).

Tempting: simplifies every consuming ADR because we can assume discrete GPU. But it kills Aether on laptops and older hardware. The real-recorded-video avatar path for Spark is achievable (it's essentially video playback + TTS), and it preserves the quality bar (it's a real person). Keep Spark.

### Retail SaaS backbone (HeyGen / D-ID / ElevenLabs cloud).

Rejected by Don: retail SaaS quality does not meet the expectation bar. Local-first remains the architectural commitment. Tiers enable that commitment across the consumer hardware range instead of forcing a single hardware assumption.

## Consequences

**Positive.**

- Aether ships on realistic consumer hardware without giving up quality.
- Tier is the one hardware-adaptation axis; no downstream ADR reinvents hardware detection.
- Existing model pins (ADR-0003) become tier-parameterised: ADR-0007 picks `bge-m3` at Flame/Forge and a smaller model at Spark, without ADR-0003 being revoked.
- User's machine is respected (50% rule); Aether is not a hostile tenant.

**Negative.**

- Three tiers × every capability subsystem (LLM, embedding, TTS, vision, avatar) = a matrix. Testing surface increases. Mitigation: per-capability integration tests at each tier will live in the consuming ADRs' execution phases, not here.
- Hardware detection has edge cases (dual-GPU laptops, eGPU, remote-desktop scenarios). Mitigation: explicit "Re-detect hardware" button, and manual override always available.
- Provisional VRAM reservations for the avatar (Decision 6) may be wrong. ADR-0008 finalises. Until then, consuming ADRs should not allocate into reserved space.

**Neutral.**

- `tier.json` is a new config file. Additive, same contract as existing files.

## Implementation notes

Run 3 implementation of this ADR needs:

1. New crate or shell module `apps/desktop/src-tauri/src/hardware.rs` — detection + tier resolution.
2. `tier.json` persistence (mirror of `memory_config.rs` pattern).
3. Tauri commands: `get_tier`, `set_tier`, `redetect_hardware`.
4. Settings drawer tier-selection UI (shows all three tiers as cards, highlights recommended).
5. Frontend TS types mirrored.
6. Rot-guard anchors added to a new `tools/lint-tier-doc/check.py` OR extended into `lint-memory-doc` (decide during implementation).
7. Migration: existing installs default to detected tier on first run post-upgrade; no tier means "not yet detected."

Estimated effort: 1 session for detection + persistence + commands, 1 session for UI + override flow, 1 session for rot-guard + docs + e2e test. **~3 sessions**.

## Open items (NOT decided here — punted to consuming ADRs or future discussion)

- Exact avatar VRAM reservations (ADR-0008).
- Which LLM runs at which tier (future ADR superseding ADR-0003's single pin).
- Which embedding model runs at which tier (ADR-0007 handles).
- TTS / vision tier manifests (future ADRs).
- Behaviour on multi-GPU systems (which adapter does detection pick?).
- Whether tier change requires app restart (punted to implementation; probably no for embeddings, yes for avatar once that exists).

---

(end of ADR-0006)
