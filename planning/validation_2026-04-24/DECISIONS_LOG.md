# Autonomous Run Decisions Log — 2026-04-24

> Every blocker-level decision Claude made during the 12 hr autonomous validation window. For Don's review on return.
> Started: 2026-04-24 session continuation after Run 3 Session A handoff.
> Authority: Don granted full autonomy including blocker-level calls; only requirement is to log them here.

---

## Locked at session start (pre-decisions)

- **Tuning commits** policy: commit + push to `dev` directly per heavy-usage protocol; review in git.
- **New ADRs** policy: ship as `Proposed` (not `Accepted`); Don ratifies on return.
- **Remediation gate**: push through soft signals; hard-stop only for panic / data loss / repo corruption / migration drift.
- **Scope**: Aether-only. Depth > breadth.

## Decisions made during the run

(Appended chronologically as work progresses.)

### D-001 — Spark default candidate: `nomic-embed-text` (not `bge-small-en-v1.5`)

ADR-0007 D7 named `bge-small-en-v1.5` as the Spark candidate. That model is on HuggingFace, not the Ollama registry — `ollama pull bge-small` returns "manifest does not exist." Per Aether's `parse_model_name` it could be loaded via `hf:org:repo:tag` but that requires HF auth + a different code path.

**Decision:** For this validation run, use `nomic-embed-text` (already pulled, 274 MB, English-language embedding model designed for semantic search) as the Spark candidate. Block 3 A/B compares bge-m3 vs nomic-embed-text. If the data shows nomic-embed-text holds quality, that becomes the new Spark default; if it lags meaningfully, this opens an open item for the team to either (a) add HF embedding support or (b) pick a different Ollama-native small embedder (e.g. `snowflake-arctic-embed:s` if it exists).

**Risk:** Low. nomic-embed-text is a credible Spark candidate independently — the original ADR-0007 author noted "or equivalent small, CPU-viable" for the Spark slot. A pivot from bge-small to nomic-embed-text is well within the spirit of D7.

**Action on Don's return:** ratify or reject the substitution. If ratified, ADR-0007 D7 gets a one-line tuning commit naming nomic-embed-text as the Spark default.

### D-002 — Inspection tooling pattern: standalone temp Cargo projects, not lib.rs restructure

Initially scoped a `apps/desktop/src-tauri/src/bin/inspect_hardware.rs` to call `hardware::detect()` + `tier::recommend_tier()` directly. Required adding `lib.rs` because the shell crate has no library target — modules are `mod foo;` not `pub mod foo;`.

**Decision:** Use cargo tests with `--nocapture` for inspection of Aether's internal types, and standalone Python / Cargo scratch projects for raw model latency / recall measurements. Reason: adding `lib.rs` to the shell crate is a real structural change (touches Cargo.toml, possibly main.rs imports, may interact with Tauri's build conventions). Worth Don's review as its own decision rather than smuggled into a validation run.

**Risk:** None. Inspection data is captured either way; the lib.rs restructure remains available as a future improvement.

**Action on Don's return:** consider adding `lib.rs` as a future ergonomic improvement if more inspection / bench work is anticipated.

### D-003 — Hardware inspection via temporary Rust project (not modify shell crate)

To validate the wgpu max_buffer_size heuristic on Don's 3090 Ti without touching the shell crate, built a standalone Cargo project at a temp dir. Uses identical wgpu 23 + sysinfo 0.32 versions.

**Decision:** captured the snapshot data; will be deleted at end of run (not committed).

**Risk:** None — temp file cleanup at wrap.

### D-004 — CRITICAL: ADR-0006 §4.C tier-detection heuristic is broken on real hardware

Hardware snapshot from inspector on Don's RTX 3090 Ti shows the wgpu max_buffer_size signal is fundamentally unreliable:

| Backend | `max_buffer_size` reported | `vram_gb_estimate` |
| --- | --- | --- |
| Vulkan | `18446744073709551615` (= u64::MAX, "unlimited" sentinel) | `4294967295` (~ 4 billion GB) |
| DX12 | `2147483647` (= 2^31-1, DX12 driver default cap) | `1` GB |
| GL | `2147483647` | `1` GB |

The current heuristic picks Vulkan (highest priority + highest "VRAM"), gets a sentinel value, divides by 2, easily exceeds the 12 GB Forge floor, returns `Forge`. **Right answer for the wrong reason.** On a system where the priority rule picks DX12 first (e.g. wgpu version drift, headless context), the same hardware would be classified `Spark`.

**Will propose ADR-0008 (Proposed status)** to fix:
- Primary signal: `device_type` only (DiscreteGpu → at least Flame; IntegratedGpu/Cpu → Spark)
- Secondary signal for Discrete vs Forge tier: `total_ram_gb` only (>= 32 GB → Forge candidate, otherwise Flame). RAM is a reliable proxy for "workstation-class system" without trusting the unreliable VRAM estimate.
- Long-term: NVML feature gate for NVIDIA on Windows/Linux to get real VRAM. (Held for follow-up ADR per ADR-0006 §Open items.)

**Action on Don's return:** ratify ADR-0008 (Proposed) or push back. Without the fix, the right tier on real hardware is essentially luck.

### D-005 — Snapshot field correctness gap

The inspector's snapshot of Don's 3090 Ti is captured at `planning/validation_2026-04-24/01_hardware_snapshot.json`. Three notable findings beyond the heuristic flaw:

- 32 logical CPU cores (Don has a workstation-class system).
- 127 GB system RAM. effective_ram per the 50% rule = 63.5 GB — passes every tier floor.
- C: drive 952 GB free. No disk pressure.
- Ollama `/api/ps` empty — no models GPU-resident at probe time. Expected; we haven't run any inference yet.



