# 14 — Performance Tiers & VRAM Policy

Hardware adaptation is a **first-class design constraint**. The product must work across weak-to-flagship systems without losing its core identity.

---

## Constraint recognition

- Many users have **limited VRAM**.
- Many users have **limited drive storage**.
- Many users have **mid-tier CPUs and mixed GPU classes**.
- The product cannot assume flagship GPU systems.
- Hardware diversity is treated as a **design constraint**, not a scaling afterthought.

---

## Three performance tiers

### Lite
**Target hardware:** low VRAM, low storage, older consumer systems.

- Smallest Gemma 4 variant (local LLM)
- 2D or minimal-3D headshot avatar
- Basic lip-sync
- Lower-resolution assets
- Reduced cache footprint
- Aggressive fallback to remote for anything beyond reflex path
- Limited local memory capacity
- Simpler presence controller

**VRAM budget: 15–25% of detected VRAM**

### Balanced
**Target hardware:** mid-range GPU or strong CPU, moderate storage.

- Mid-size Gemma 4 variant
- Improved avatar quality (gaze, blink, listening/thinking states distinct)
- Better lip-sync quality
- Stronger local reflex stack — more tasks stay local
- More persistent assets and cache
- Better local memory capacity
- Balanced between local and remote deliberative

**VRAM budget: 30–40% of detected VRAM**

### Full / Pro
**Target hardware:** high-end GPU, larger storage budget.

- Largest Gemma 4 variant the VRAM budget supports
- Highest-fidelity local runtime
- Richer avatar: full facial animation, idle motion, gesture scheduling (later)
- Larger persistent model and asset packs
- Most tasks handled locally; remote only for hardest deliberative work
- Richer local memory with wider retrieval
- Full presence controller active

**VRAM budget: 50% of detected VRAM (default)**

---

## VRAM policy (the 50% rule)

### The rule
**The fully installed Pro product targets ~50% of available VRAM as its default local budget ceiling.**

### Why not 100%
Filling VRAM tightly causes:
- Rendering stalls (avatar mode, desktop compositor)
- Framework/allocator overhead spikes
- Fragmentation degradation over long sessions
- Concurrency collapse when another app needs GPU
- Thermal / power pressure on laptops
- General system instability

### Budget envelope (default policy)

| Tier | VRAM budget | Rationale |
|------|-------------|-----------|
| Lite | 15–25% | Maximum headroom; product works on shared-GPU systems |
| Balanced | 30–40% | Room for rendering and other apps |
| Full / Pro | 50% (default) | Premium experience; other apps still work |
| Expert override | User-adjustable higher | Warnings shown; user accepts instability risk |

### Not a hard law
The 50% target is a **default envelope**, not a hard rule for every subsystem. Subsystems within Aether share the budget intelligently — avatar rendering, local LLM, memory embedding index, visual state.

Advanced users can raise the cap in settings with explicit warnings.

---

## Storage strategy

### Modular packs
Heavy components are **installable as packs**, not bundled as always-present:

- **Model packs** — Gemma 4 variant sizes (Lite / Balanced / Full)
- **Voice packs** — TTS voices
- **Avatar asset packs** — persona appearances
- **Language packs** — additional languages for STT/TTS
- **Advanced tool packs** — browser, file, research, coding tool suites
- **Cache packs** — larger local inference caches for Pro

### Storage budget
- User controls retention.
- Onboarding shows install footprint per choice.
- Settings surfaces current storage use per component with "remove" options.
- Cache eviction is automatic with configurable limits.

### No bundled bloat
- OSS Preview install is intentionally small (Tauri-class footprint advantage).
- Larger components downloaded only when user opts in.
- Pro install is modular — users can start lean and add packs.

---

## Hardware detection (onboarding + runtime)

### Detection inputs
Runs automatically during onboarding (Step 4 in [06_onboarding_spec.md](06_onboarding_spec.md#step-4-hardware-performance)):

- **VRAM** — total + free + class (low/mid/high)
- **Storage** — total capacity, free space
- **CPU** — class, core count
- **Microphone** — available, permitted
- **Camera** — available, permitted (optional for user-attention signal)
- **Network** — quality, latency to common endpoints

### Detection outputs
- **Recommended performance tier**
- **Recommended default model pack size**
- **Recommended asset pack sizes**
- **Warnings** (e.g., "Your system has limited VRAM; Full tier may be unstable")
- **Estimated install footprint per tier**

### User override
Auto-detection never silently applies. The onboarding shows the recommendation; the user can accept or override. Advanced override available in settings later.

### Runtime re-detection
- Hardware detection re-runs on startup (for users who upgrade GPUs).
- Tier recommendation updates.
- If a significant change is detected, user is prompted to reconsider tier.

---

## Local LLM: Gemma 4 variants per tier

**Gemma 4 is the default local LLM across all tiers.** Variant sizing scales with hardware:

| Tier | Reflex path | Local deliberative | Remote fallback |
|------|-------------|--------------------| ----------------|
| Lite | Smallest Gemma 4 variant | N/A — always remote | Frontier LLM (required for non-reflex tasks) |
| Balanced | Mid Gemma 4 | Mid Gemma 4 handles most | Frontier LLM for edge cases |
| Full / Pro | Largest Gemma 4 within 50% VRAM | Largest Gemma 4 | Frontier LLM only for hardest tasks |

Variant selection is automatic during onboarding based on detected VRAM. Advanced users can select larger or smaller variants with warnings.

---

## Runtime tier behavior

### Dynamic adjustment
- If VRAM pressure is detected during runtime, the system can **downgrade dynamically** (e.g., reduce avatar rendering fidelity) rather than crash.
- User is notified via the trust center.
- Tier preference is preserved; only the active runtime behavior adjusts temporarily.

### Tier-specific defaults
Settings honor tier context: defaults shown on a Lite system differ from defaults on a Pro system. The info-explainer for each setting notes "Recommended for your tier."

### Cross-tier consistency
The **product identity is the same across tiers.** Only the performance ceiling changes. A Lite user should feel they're using the same product as a Pro user — just with lighter local capability.

---

## OSS Preview scope

The OSS Preview supports:
- **Lite** (default for most systems)
- **Balanced** (where hardware allows)
- **Optional Enhanced mode** for stronger systems (exposes a subset of Full capabilities)

The Preview does not expose the full three-tier ladder. Full-tier experience is a Pro milestone.

---

## Pro scope

Aether Pro supports the full **Lite / Balanced / Full** ladder with:
- Dynamic tier adjustment
- Expert overrides
- Full modular pack system
- Per-pack install / remove management

---

## Anti-patterns (rejected)

- **Assume flagship GPU** — blocks mainstream users from the product.
- **Fill 100% of VRAM for "maximum quality"** — unstable, destructive to other apps.
- **Require the user to understand VRAM / tokens / inference** — jargon is behind advanced settings only.
- **Silent tier degradation** — always surface what the system is doing.
- **Bundled-everything installs** — storage hostile; user should control what's installed.

---

## Cross-references
- Onboarding Step 4: [06_onboarding_spec.md](06_onboarding_spec.md#step-4-hardware-performance)
- Realtime model / Gemma 4 usage: [09_realtime_interaction.md](09_realtime_interaction.md#default-local-llm-gemma-4)
- Tech stack (Gemma 4 runtime): [16_tech_stack.md](16_tech_stack.md)
- Trust center (dynamic adjustment disclosure): [13_trust_security_redteam.md](13_trust_security_redteam.md)
