# Handoff — 2026-04-24 Milestone 2 Run 3 Session A (BACKEND COMPLETE)

**Written:** 2026-04-24 session end (continuation after Run 2 close).
**Branch:** `dev`. Tip `0eb7c65`. All commits pushed to `origin/dev`.
**Working tree:** clean.

Run 3 Session A — the backend half of Embeddings Onboarding under the new ADR-0006 hardware tier model — is complete. Every Tauri command and AppState method the Session B UI will consume is shipped, tested, and rot-guarded. No real model loads were triggered during this session (light-usage protocol respected throughout); on-hardware validation is the next gate.

---

## 1. Commit table (Session A)

| SHA | Subject |
| --- | --- |
| `74bdd0e` | deps(shell): add sysinfo + wgpu + ureq for ADR-0006/0007 wiring |
| `5f4b917` | feat(hardware): ADR-0006 detection module — wgpu + sysinfo + ollama probe |
| `c2ac0e8` | feat(tier): ADR-0006 Tier enum + tier.json persistence + recommend_tier |
| `e98eab2` | feat(retrieval,state): ADR-0007 D3 readiness state machine |
| `f87facf` | feat(state): wire tier_config + tier-aware accessors into AppState |
| `b353944` | feat(commands,main): tier + readiness Tauri command surface + boot detect |
| `490a3f3` | feat(retrieval,state,main): ADR-0007 D2+D8 readiness probe + boot wiring |
| `0eb7c65` | docs+ts(adr-0006/0007): rot-guard anchors + frontend TS mirrors |

Eight commits, all pushed.

---

## 2. What shipped

### Hardware detection (ADR-0006 D2)

- `apps/desktop/src-tauri/src/hardware.rs` — pure-read detection module.
- `wgpu::Instance::enumerate_adapters` for cross-platform adapter list (Vulkan / Metal / DX12 / GLES).
- `sysinfo` for RAM + CPU cores; `sysinfo::Disks` for cross-platform disk space.
- Optional 750ms `GET /api/ps` probe via `ureq` to detect Ollama-loaded-on-GPU state. No model loads.
- `HardwareSnapshot` + `GpuInfo` + `GpuKind` types with snake_case serde for TS mirroring.
- 7 unit tests; sandbox-safe (works with no GPU drivers, no Ollama).

### Tier model + persistence (ADR-0006 D1, D3, D7)

- `apps/desktop/src-tauri/src/tier.rs`.
- `Tier` enum (Spark / Flame / Forge), `TierConfig` (selected_tier, detected_tier, detected_at_ms, manual_override, hardware_snapshot).
- `recommend_tier` implements ADR-0006 §Decision 3 — highest-tier-meeting-envelope rule, with the 50% headroom applied at recommendation time only (quality-first amendment: not a runtime cap).
- Same persistence contract as `memory_config.rs` and `presence_config.rs`: additive serde, default-safe on read, unknown fields ignored, malformed JSON → defaults + WARN, atomic write.
- 16 unit tests covering the full recommendation matrix (no GPU, integrated, low-discrete, mid-discrete, high-discrete, low-RAM, high-VRAM-low-RAM corner case) plus persistence + serde shape.

### AppState integration (ADR-0006 D5, ADR-0007 D3)

- `tier_config: RwLock<TierConfig>` + `tier_config_path: Option<PathBuf>` fields.
- `attach_tier_config_file`, `tier_config()`, `set_tier(tier)`, `redetect_hardware()`.
- `redetect_hardware` honours manual override: if user previously chose a non-detected tier, detection updates `detected_tier` only.
- `retrieval_readiness: RwLock<ReadinessState>` field + `retrieval_readiness()` / `set_retrieval_readiness()` accessors.
- `probe_readiness_now()` — assembles inputs from live state, runs the ADR-0007 D2+D8 probe, stores result, returns it for synchronous reaction.
- `set_memory_config` triggers a settings-change probe after persisting policy changes.

### Retrieval readiness state machine (ADR-0007 D3)

- `ReadinessState` enum (Unknown / Disabled / Ready / NotReady{reason}).
- `NotReadyReason` enum (ProviderUnreachable, ModelNotInstalled, PolicyDenied, EmbedFailed, Bailout, LowDisk).
- Both with `tag = "kind"` snake_case serde for stable TS wire shape.
- `run_retrieval_context` updates state symmetrically — failure paths flip to NotReady, success path flips to Ready. Recovery is automatic on next successful turn (no background poll).
- 6 retrieval tests + 6 probe tests verifying state transitions + wire form.

### Readiness probe (ADR-0007 D2 + D8)

- `retrieval::probe_readiness` — pure decision function.
- Order: enabled-check → provider-set check → disk-space preflight (model_size × 1.5) → /api/tags HTTP probe → model-listed check → Ready.
- `required_disk_gb_for_provider` — bakes in safety multiplier; bge-m3 = 2 GB, bge-small = 1 GB, unknown = 2 GB conservative.
- `parse_model_name` — strips `ollama:` / `hf:org:repo:` prefixes.
- Local 10-line JSON parse (avoids cross-layer dep on l4-router's feature-gated `parse_tags_response`).

### Tauri commands (ADR-0006 + ADR-0007)

- `get_tier` → `TierConfig`
- `set_tier(tier)` → `TierConfig`
- `redetect_hardware` → `TierConfig`
- `embeddings_readiness` → `ReadinessState`
- All registered in `main.rs` `invoke_handler!`. Wire shapes match Rust 1:1.

### Boot wiring

- After memory_config attach, before vision/voice registries:
  1. Attach `tier.json` via `attach_tier_config_file`.
  2. Run `redetect_hardware` (light-usage; tracing::warn on failure, no crash).
  3. Run `probe_readiness_now` (light-usage; tracing::info on result).

### Frontend TS mirrors

- `apps/desktop/src/lib/types.ts`: `Tier`, `GpuKind`, `GpuInfo`, `HardwareSnapshot`, `TierConfig`, `NotReadyReason`, `ReadinessState`. All precise serde mirrors of the Rust types.
- `apps/desktop/src/lib/api.ts`: `getTier()`, `setTier(tier)`, `redetectHardware()`, `embeddingsReadiness()`. 1:1 with Tauri commands.

### Rot guard (ADR-0006 + ADR-0007)

- `tools/lint-memory-doc/check.py` gained 21 new anchors across 5 new files.
- 79 → 100 anchors across 19 → 24 files. Check passes.

---

## 3. Check matrix (post-session)

| Check | Result | Delta vs Run 2 close |
| --- | --- | --- |
| `git status` | clean | — |
| Commits ahead of `origin/dev` | 0 (pushed) | — |
| `cargo fmt --all -- --check` | clean | — |
| `cargo check --all-features` (shell) | clean | — |
| `apps/desktop/src-tauri cargo test --all-features` | **265 / 265** | +35 (was 230) |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings" --test sqlite_session` | 23 / 23 | unchanged |
| `cargo test --workspace` | all green | unchanged |
| `python tools/lint-memory-doc/check.py` | **OK 100 / 24** | +21 anchors / +5 files |
| `python tools/lint-quality-doc/check.py` | OK 60 / 19 | unchanged |
| `tools/evals --dry-run` | 6 / 6 | unchanged |
| `tsc --noEmit` (apps/desktop) | clean | unchanged |
| vitest (apps/desktop) | 188 / 188 | unchanged |

---

## 4. Risks / alerts

### A. (CARRIED) `gemma4:e4b` + `bge-m3` + `bge-small-en-v1.5` unverified on real hardware.

ADR-0007 D7's per-tier latency estimates and the Spark embedding default pin (`bge-small-en-v1.5` candidate) remain estimates pending the on-hardware validation gate. This is the single remaining blocker for Run 3 implementation closure. ~15-30 min of Don's GPU time.

### B. (CARRIED) Augmented utterance reaches L1 audit trail.

Risk G from HANDOFF_2026-04-24_M2_RUN_2_COMPLETE.md. Memory and transcript still see the original utterance via `user_record_raw`; only the L1 audit dashboard (which doesn't exist as a UI yet) would see the augmented form. Cross-layer fix → future ADR.

### C. (NEW) `wgpu::Limits::max_buffer_size` is a single-allocation ceiling, not total VRAM.

Documented inline in `hardware.rs` and ADR-0006 §Decision 2. Tier recommendation uses GPU device type (Discrete vs Integrated vs Cpu) as the primary signal and `max_buffer_size` as a hint, not a truth. NVML / IOKit refinements deferred to a future ADR per ADR-0006 §Open items. **First on-hardware validation will reveal whether the heuristic picks the right tier on Don's actual machine** — this is the most likely thing to need refinement post-validation.

### D. (NEW) Multi-GPU / eGPU / remote-desktop edge cases unhandled.

ADR-0006 D2 documents this as "intentionally unresolved": default-adapter selection picks highest-VRAM discrete, manual override covers cases where automatic picks wrong. Re-visit if reports warrant.

### E. (RETIRED) Run 2 risks A, F.

Run 2 risks fully retired in this session: retrieval is live on real turns (Run 2 risk A, retired in earlier handoff), and the `Arc<AppState>` ownership concern (Run 2 risk F) was sidestepped — never needed an Arc-of-self for any wiring.

### F. (CARRIED) `set_tier` does not yet emit a `tier_changed` event.

ADR-0006 D5 specifies that subsystems should re-read tier on `tier_changed` event emission. Today, only `set_memory_config` triggers a downstream `probe_readiness_now`. When future tier-aware subsystems (TTS, vision, avatar) land, they'll need the event bus wiring. Trivial follow-up; flagged so it doesn't get rediscovered later.

---

## 5. Decisions log

Milestone 2:
- **#M2-01..#M2-05, #M2-09..#M2-15** — RESOLVED earlier (ADR-0003, 0004, 0005).
- **#M2-06 / #M2-07 / #M2-08** — reserved (future runs — Gap #3 auth, CI ADR, CI blocking).

ADR-0006 + ADR-0007 numbered decisions:
- **ADR-0006 D1..D7** — all implemented this session.
- **ADR-0007 D1..D9** — all implemented this session except D5 backfill (Session B) and D6 indicator surface (Session B). The state machine, probe, disk preflight, and tier-aware model manifest are all backend-ready for the UI to consume.

No new numbered decisions. Implementation flowed directly from the accepted ADRs without blocking design questions — clean ADR → code execution.

---

## 6. Next session prompt — Run 3 hardware validation + Session B kickoff

Paste-verbatim block:

````md
You are Claude Code, opening the post-Session-A phase of Milestone 2
Run 3 for Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev. Session-start tip should be `0eb7c65` or later (verify
with `git log --oneline -10`).

SESSION TYPE
- HEAVY-USAGE: this session begins with on-hardware validation of
  ADR-0007 D7's latency estimates and the Spark embedding default
  pin. Don will pull models, flip the embeddings flag, submit two
  turns. Claude observes the outcomes and either (a) confirms the
  estimates, (b) tunes them via a single-file commit on
  ADR-0007.md, or (c) opens a remediation ADR if something
  unexpected surfaces.
- After validation closes, the session may proceed to Session B
  light-usage prep: Trust drawer RetrievalTab scaffolding, attention
  badge stub, toast infrastructure (UI-shaped — Don should be
  consulted on visual decisions).

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `python scripts/current_status.py` — should surface this
   handoff (HANDOFF_2026-04-24_M2_RUN_3_SESSION_A_COMPLETE.md).
2. `git log --oneline -15` — confirm 0eb7c65, 490a3f3, b353944
   in history.
3. Read in order:
   - This handoff (§4 risks, §6 next-session prompt).
   - `docs/adr/ADR-0006-hardware-tier-model.md` (Accepted).
   - `docs/adr/ADR-0007-embeddings-onboarding.md` (Accepted).
   - `apps/desktop/src-tauri/src/retrieval.rs` (probe + state).
   - `apps/desktop/src-tauri/src/tier.rs` (recommend_tier).
   - `apps/desktop/src-tauri/src/hardware.rs` (detection).

================================================================
§PHASE 1 — On-hardware validation (HEAVY-USAGE)
================================================================

Confirm with Don he is prepped:
- Other GPU-heavy apps closed (browser tabs minimised, no games,
  no ComfyUI).
- Heavy-usage env vars set per Bucket A defaults from prior
  discussion: `OLLAMA_MAX_LOADED_MODELS=2`,
  `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_FLASH_ATTENTION=1`.
- Ollama running.

Validation script:
1. `ollama pull gemma4:e4b && ollama pull bge-m3`. Note pull time
   + size.
2. Edit `<app_data>/memory.json`: set
   `embeddings.enabled = true` and
   `embeddings.provider = "ollama:bge-m3"`.
3. Launch Aether (debug build). Note:
   - Tier auto-detected (expect Flame or Forge given Don's LoRA
     history).
   - `embeddings_readiness` initial state in logs (expect
     `Ready` after both models pulled).
4. Submit turn 1 with content Aether could later reference (e.g.
   "I'm planning a trip to Iceland in October").
5. Submit turn 2 with a reference (e.g. "What did I say I was
   planning?"). Tracing should show:
   - `run_retrieval_context` invocation.
   - Block `Relevant context (retrieval):` appearing in the
     prompt the router forwards.
   - Hit pointing at turn 1's content.
6. Capture: cold-start time on first embed call, warm latency on
   second, approximate retrieval block size.

Outcome handling:
- Estimates within ±2× of ADR-0007 D7's table → confirm; commit
  a one-liner on the ADR noting "validated on Don's hardware
  YYYY-MM-DD."
- Significantly off → tune the table; commit. Note the actual
  hardware spec snapshot in the ADR.
- Anything weird (panics, missing models, retrieval block doesn't
  appear, FA hangs) → STOP. Open a remediation ADR; do not
  proceed to Session B until resolved.

================================================================
§PHASE 2 — Session B kickoff (LIGHT-USAGE; UI-shaped)
================================================================

Only proceed if Phase 1 outcome is "validated" or "tuned." If
remediation ADR opened, stop here and hand off to Don for review.

Session B work is UI-shaped. Don should be consulted on visual
decisions. Light-usage prep that doesn't require Don's taste:

- Frontend types are already shipped (`getTier`, `setTier`,
  `redetectHardware`, `embeddingsReadiness` in api.ts; `Tier`,
  `TierConfig`, `ReadinessState`, `NotReadyReason` in types.ts).
- Component skeletons (RetrievalTab, ReadinessIndicator) can be
  scaffolded with placeholder layouts that import the types and
  pass typecheck.
- Toast infrastructure (if Aether already has a toast pattern,
  reuse; if not, this is a Don-decision).

Visual decisions to escalate:
- Where the indicator lives in the chrome (Trust drawer? new
  drawer? badge on the existing drawer icon?).
- Toast styling and duration.
- "Backfill now" button placement and progress UI.
- CLI-pull instruction copy + selectable text rendering.

================================================================
§DELEGATED DECISIONS
================================================================

- Tuning ADR-0007 D7 table values from real measurements: Claude
  may revise within reason. If a model is so slow it changes
  tier classification (e.g. bge-m3 takes minutes on Don's box),
  escalate.
- Whether Spark embedding default stays `bge-small-en-v1.5` or
  changes — open item in ADR-0007. Validation may suggest
  alternatives.

================================================================
§DONE WHEN
================================================================

- Validation outcome captured (one of: validated / tuned /
  remediation-opened).
- ADR-0007 D7 table reflects measured reality OR an explicit
  follow-up is filed.
- Session B kickoff scaffolding shipped if Phase 1 succeeded
  AND Don agreed to the visual decisions.
- Standard session-end: full check matrix, execution report,
  handoff with commit table + next prompt, push.

================================================================
§STANCE
================================================================

Phase 1 is information-gathering, not implementation. Resist the
urge to "fix" anything in code based on validation results until
the data is captured and a clean tuning commit can be made.

Phase 2 stops at the first visual decision that needs Don. Don't
guess; ship a scaffold and wait.

Good luck.
````

---

## 7. Lessons learned (Run 3 Session A)

### Engineering / craft

1. **`wgpu::Limits::max_buffer_size` is not total VRAM.** It's a single-allocation ceiling. On a 24 GB card, Vulkan often reports a 4 GB limit. Tier detection that uses it as a VRAM proxy is *suggestive*, not authoritative. The tier-recommendation rule was rewritten to use device type (Discrete / Integrated / Cpu) as the primary signal and the VRAM estimate as a tiebreaker — exactly because the estimate is unreliable in absolute terms but the *ordering* (a 4090 reports more max-buffer than a 4070) holds. NVML / IOKit will be needed for tighter numbers when real users start hitting the boundary cases.

2. **Windows `std::fs::canonicalize` adds a `\\?\` extended-path prefix that breaks `Path::starts_with` against any path that doesn't have that prefix.** Hit this in the disk-space probe when comparing canonicalized tempdir paths against `sysinfo::Disk::mount_point()`. Fix: walk-up to existing parent without canonicalizing. Generalizable rule: if you're going to string-compare path prefixes on Windows, don't canonicalize first.

3. **wgpu API churns between minor versions.** wgpu 23 changed `Instance::new(&InstanceDescriptor)` to `Instance::new(InstanceDescriptor)` (by value, not by reference) and renamed the `gles` feature to `glsl`. The `default-features = false` + custom feature list was over-engineering for adapter enumeration; default features work fine since we don't actually render. Lesson: when adding a new heavy dep, start with `crate = "version"` (no feature pruning), get it working, then prune if there's a measurable build-time payoff. Premature pruning costs more than it saves.

4. **`parse_tags_response` lives in `aether-l4-router::providers::ollama_vision` behind the `ollama-provider` feature gate.** Not exported from `lib.rs`. Cross-layer reuse would have required adding a `pub use` (cross-layer change, requires its own session per repo CLAUDE.md). Instead: duplicate the 10-line JSON parse locally. The duplication is fine because the wire shape is anchored by an existing test; drift will be caught.

5. **`Cargo.lock` for the Tauri shell is gitignored.** `git add -A apps/desktop/src-tauri/Cargo.lock` errored because the file is in `.gitignore`. Just stage `Cargo.toml`; the lock regenerates on each build. This is intentional for app crates (vs library crates where the lock is committed).

6. **`Disks::new_with_refreshed_list()` from `sysinfo` 0.32 is enough for cross-platform disk-space probing — don't reach for `libc::statvfs` or Windows FFI.** Initial draft used `cfg(unix)` + `libc::statvfs` and `cfg(windows)` + raw `GetDiskFreeSpaceExW` FFI. Way over-engineered. `sysinfo`'s `Disks::list()` enumerates disks with `mount_point()` and `available_space()`; longest-mount-point match against the canonical-ish path gives the correct disk on every platform with no `unsafe`. Removed ~60 lines of FFI by switching.

### Process / methodology

7. **Accepted ADRs as input → frictionless implementation.** ADR-0006 + ADR-0007 were drafted, reviewer-edited, and accepted *before* any code was written. Implementation took 8 commits across one focused session with zero "wait, what should this do?" moments. Every numbered decision had a clean home in code. By contrast, Run 2 had two design questions that only surfaced during implementation and required mid-session decisions (the path-(b) wiring, the `user_record_raw` split). The ADR-first cycle is materially smoother.

8. **The "one layer per session" repo rule held throughout.** Every change this session was inside `apps/desktop/src-tauri/src/*` or `apps/desktop/src/*` or `tools/lint-memory-doc/`. No `packages/l*` modifications. The temptation to add `pub use parse_tags_response` to L4 was real and was consciously rejected via local duplication. Discipline paid off — the rule's anti-drift property held.

9. **Heavy-usage protocol works.** Eight commits shipped, 100% light-usage (compile, stub-tested, no model loads, no GPU memory allocated). Don could have been asleep through the entire session. The protocol's value is exactly this: it lets Claude make real progress without blocking on Don's hardware availability. The next gate (validation) is the *first* heavy-usage moment in the entire Run 3 backend.

10. **Quality-first amendments (the ADR-0006 D3 + ADR-0007 D7 reframes) saved scope.** During the optimization-strategies discussion, the temptation to add lazy embedder loading, aggressive `KEEP_ALIVE=30s`, `num_ctx=8192` caps, and async embed-on-write queues was real. Each would have shaved VRAM at quality cost. Locking the quality-first posture in writing meant they were rejected by *policy* during this session rather than re-debated case-by-case. Saved probably 200+ LOC and a half-day of decisions.

11. **The Bucket A / Bucket B / Bucket C split was the right model.** When Don asked "are these your-machine optimizations or general defaults?", the three-way taxonomy (architecture-required for everyone / user-preference exposed in Settings / situational power-tool tweaks) cleanly classified every recommendation. Without that split, the optimization-strategies message would have been a confusing list. With it, the boundary between "Aether ships this for everyone" and "Don turns this on when he's doing heavy work" was unambiguous.

12. **Atomic small commits paid off mid-session.** When the disk-probe test failed (`\\?\` prefix issue), the fix was localized to one function and shipped as a follow-up; no large rollback needed. Each of the 8 commits this session is independently reversible and reviewable. Compare to a hypothetical 1500-line "Run 3 Session A" megacommit that would have been impossible to bisect.

### Aether-specific

13. **The `submit_turn` augmented-utterance approach (ADR-0005 D2 path-b) keeps paying dividends.** Run 3 added 4 new Tauri commands and a state machine; none required `Arc<AppState>` or `Weak<Self>` gymnastics inside the router because the router stays prompt-string-only. Path (a) would have meant breaking `AppState::build_active`'s `&self` ownership pattern. Glad past-Don signed off on path (b).

14. **`StubEmbedder` is sufficient for backend-shape verification.** Every retrieval test, probe test, and state-machine test used `StubEmbedder` (or skipped the embed path entirely). The shape of the implementation is correct without ever hitting Ollama. Real-world scoring distributions will need real models eventually, but for state machine correctness, control flow, error paths, and serde shapes — stubs are enough. This is what enables the heavy-usage protocol to work.

15. **Boot-path failures must always degrade to `tracing::warn` + default state, never panic.** Both `redetect_hardware()` and `probe_readiness_now()` return `Result`s the boot path swallows with `tracing::warn!` / `tracing::info!`. The shell never refuses to start because a probe failed. The state machine self-heals on next real turn (D3 symmetric event-driven cadence). Without this discipline, a flaky Ollama connection at boot could brick the app on first launch — exactly the failure mode users least tolerate.

---

## 8. Session totals

Eight commits, +35 shell tests (230 → 265), +21 rot-guard anchors (79 → 100, +5 files), 2 new modules (`hardware.rs`, `tier.rs`), 4 new Tauri commands, 7 new TypeScript types/interfaces.

No code touches `packages/l*-*/`. Layer boundary held.

Cumulative Milestone 2: 19 commits, 4 ADRs accepted (0003, 0004, 0005 prior; 0006 + 0007 this session — actually 5), 3 onboarding/runtime subsystems shipped (Durable lane, retrieval wiring, tier model + readiness).

---

## 9. Session-end gate

- [x] All Run 3 Session A backend tasks (9 of 9) completed.
- [x] All commits pushed to `origin/dev`.
- [x] Full check matrix green.
- [x] Heavy-usage protocol respected (zero model loads, zero GPU memory allocated).
- [x] Lessons learned captured.
- [ ] On-hardware validation (next session, heavy-usage gate).

---

(end of handoff)
