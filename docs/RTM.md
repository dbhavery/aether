# Light Requirements Traceability Matrix (RTM)

> **Status:** Initial draft 2026-05-18 — closes Spec Gap #5 from
> `HANDOFF_2026-05-18_ALL_NIGHTER_TIER_1_PLUS_2A.md`.
> **Scope:** A *lightweight* mapping from each load-bearing
> architectural requirement → the implementation surface that
> satisfies it → the test or rot-guard that exercises it. Heavy
> formal RTM (per-AC numbering, bidirectional traceability,
> coverage percentages) is **out of scope**.
>
> **How to read this:**
>
> - **Requirement** is a paraphrased one-liner from the canonical
>   spec section. The Source-doc link is the authoritative wording.
> - **Implementation surface** lists concrete code paths. When a
>   requirement spans multiple files, the most load-bearing one is
>   listed first.
> - **Test / rot-guard** names a unit / Vitest test, a rot-guard
>   manifest entry, or both. Per
>   [`docs/GLOSSARY.md`](file:///C:/Users/dbhav/Projects/aether/docs/GLOSSARY.md)
>   §6 rot guards are doc/code consistency checks, **not** acceptance
>   criteria — a rot guard alone is a weaker citation than a
>   behavioural test.
> - **Status** values:
>   - **Implemented** — code path exists, behaviour shipped,
>     verified with `grep -l` against the cited symbol/path.
>   - **Partial** — shipped for a subset (one platform, one
>     domain, one tier) with the rest deliberately deferred.
>   - **Stub** — surface reserved (trait + no-op default, schema
>     additions, env-var contract) but no behaviour wired yet.
>
> Coverage target: load-bearing requirements only, ~30–50 rows.
> Requirements that are pure documentation hygiene (clickable
> links, doc tone) are excluded. New ADRs add new rows; this file
> is hand-maintained, not generated.

---

## 1. Memory V2 — six-domain memory + retention + embeddings

Source: [`docs/MEMORY-V2-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md)

| # | Requirement | Source doc § | Implementation surface | Test / rot-guard | Status |
|---|-------------|--------------|------------------------|------------------|--------|
| M1 | Six memory domains (Session, Durable, Facts, Projects, Preferences, Artifacts) freeze the v2 schema | [§1](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) | [`packages/l2-memory/src/domain.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l2-memory/src/domain.rs) | `tools/lint-memory-doc/check.py` ANCHORS + `cargo test -p aether-l2-memory` | Implemented |
| M2 | `memory.json` is additive + default-safe + atomic-write + single-writer through `MemoryPolicyRegistry` | [§3](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/memory_config.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/memory_config.rs) | `memory_config::tests::*` (atomic write, default-on-malformed) + `tools/lint-memory-doc/` | Implemented |
| M3 | User-sensitive domains (Facts, Artifacts) default to `Ask` write policy; standard domains route Auto | [§4](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) | [`packages/l2-memory/src/sqlite_session.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l2-memory/src/sqlite_session.rs), [`packages/l5-policy/src/capability.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/capability.rs) (`MemoryWrite`/`MemoryRead`/`MemoryForget`/`MemoryEdit`) | `cargo test -p aether-l5-policy capability::` | Implemented |
| M4 | Retention sweep runs at boot + hourly tick; aggregates one `memory_forgotten` row per domain | [§10 step 5](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/memory_service.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/memory_service.rs) `run_retention_sweep`, [`apps/desktop/src-tauri/src/main.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/main.rs) `RETENTION_SWEEP_INTERVAL_MS` | `memory_service::tests::run_retention_sweep_*` | Partial — Session + Durable only; Facts/Projects/Preferences/Artifacts trace-skipped per ADR-0005 |
| M5 | Embeddings opt-in; `embeddings.enabled = false` default; provider failure is best-effort and never blocks the primary write | [§10 step 6](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) | [`packages/l2-memory/src/embeddings.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l2-memory/src/embeddings.rs) `maybe_embed_on_write` | `cargo test -p aether-l2-memory --features embeddings` | Implemented |
| M6 | Retrieval wiring grounds turns when embeddings on; `RetrievalContext` audits one row per invocation; 5 s wall-clock bailout | [§10 step 8](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) + [ADR-0005](file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0005-retrieval-wiring.md) | [`apps/desktop/src-tauri/src/retrieval.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/retrieval.rs) `run_retrieval_context` / `format_retrieval_block` | `retrieval::tests::*` + `tools/lint-memory-doc/` | Implemented |
| M7 | Audit row schema v2 carries `original_utterance` + `retrieval_provenance`; pre-2026-04-25 rows deserialize as v1 via `serde(default)` | [§10 ADR-0009 callout](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) + [ADR-0009](file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md) | [`packages/l5-policy/src/audit.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit.rs), [`apps/desktop/src/components/TrustDrawer.tsx`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/TrustDrawer.tsx) | `cargo test -p aether-l5-policy audit::schema_v2*` + `TrustDrawer.test.tsx` | Implemented |
| M8 | Embedding backfill is user-initiated, skip-already-embedded fast path, gated by `Capability::RetrievalContext` | [§9 backfill](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) + [ADR-0007](file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0007-embeddings-onboarding.md) | [`apps/desktop/src-tauri/src/backfill.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/backfill.rs) | `backfill::tests::skip_already_embedded*` | Implemented |
| M9 | U+FFFD sanitization on embedding input — default trait method on `EmbeddingProvider::embed` | [§9 sanitization](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) | [`packages/l2-memory/src/embeddings.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l2-memory/src/embeddings.rs) | `embeddings::tests::sanitize_replacement_character` | Implemented |
| M10 | Memory tab in TrustDrawer = read + forget + edit (NOT write); per-domain lanes | [§6](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) | [`apps/desktop/src/components/MemoryTab.tsx`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/MemoryTab.tsx) | `MemoryTab.test.tsx` | Implemented |
| M11 | No raw media bytes ever enter memory; vision/voice persist only text descriptions | [§7 + §8 hard constraint 1](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/commands.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs) `analyze_frame` (transient `data:image/...` payload) | `commands::tests::analyze_frame_does_not_persist_bytes` (defensive) + `tools/lint-memory-doc/` | Implemented |

---

## 2. Presence V1 — attention/posture axes + threshold editor

Source: [`docs/PRESENCE-V1-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md)

| # | Requirement | Source doc § | Implementation surface | Test / rot-guard | Status |
|---|-------------|--------------|------------------------|------------------|--------|
| P1 | Two orthogonal axes — assistant posture + user attention — exposed as distinct snapshots / Tauri commands | [§0–§2](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md) | [`packages/l3-presence/src/controller.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l3-presence/src/controller.rs), [`packages/l3-presence/src/attention.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l3-presence/src/attention.rs) | `cargo test -p aether-l3-presence` + `tools/lint-presence-doc/check.py` | Implemented |
| P2 | Attention thresholds (`idle_after_s = 120`, `away_after_s = 600`) configurable; `away` coerced to `idle + 1` if invalid | [§2 thresholds](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md) | [`packages/l3-presence/src/attention.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l3-presence/src/attention.rs) `AttentionThresholds`, [`apps/desktop/src-tauri/src/presence_config.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/presence_config.rs) | `attention::tests::thresholds_*` | Implemented |
| P3 | 1 Hz poll loop; transition-only emission (no event when state holds) | [§1 + §8 constraint 11](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/main.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/main.rs) `run_presence_loop`, `PRESENCE_POLL_MS` | Behavioural via shell smoke + `tools/lint-presence-doc/` | Implemented |
| P4 | `presence.json` additive + default-safe + atomic-write + single-writer | [§3](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/presence_config.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/presence_config.rs) | `presence_config::tests::*` | Implemented |
| P5 | Presence does NOT write `AuditRecordEvent`s — observation, not policy-gated action | [§5 + §8 constraint 6](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md) | (negative requirement — no L5 call sites in `run_presence_loop`) | `tools/lint-presence-doc/check.py` (anchors `AuditRecordEvent`-free) | Implemented |
| P6 | Windows idle probe via `GetLastInputInfo`; macOS/Linux return `None` | [§9 real idle probes](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/idle_probe.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/idle_probe.rs) `WindowsIdleProbe` / `UnsupportedIdleProbe` | `idle_probe::tests::*` | Partial — Windows only; mac/Linux V2 |
| P7 | Runtime renderer scaffold (`Renderer` trait + `LogStubRenderer` no-op) reserves avatar-input contract | [§9 L3 avatar rendering](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md) | [`packages/l3-presence/src/runtime.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l3-presence/src/runtime.rs) | `runtime::tests::log_stub_emits_renderer_events` | Stub (intentional) |
| P8 | Settings threshold editor + history toggle + enabled toggle | [§4](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md) | [`apps/desktop/src/components/SettingsDrawer.tsx`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/SettingsDrawer.tsx) | `SettingsDrawer.test.tsx` | Implemented |

---

## 3. Vision V1 — single-frame capture + provider gate

Source: [`docs/VISION-V1-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md)

| # | Requirement | Source doc § | Implementation surface | Test / rot-guard | Status |
|---|-------------|--------------|------------------------|------------------|--------|
| V1 | `analyze_frame` evaluates media-permission tri-state before invoking provider | [§1 step 2](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/commands.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs) `analyze_frame`, [`apps/desktop/src-tauri/src/media_permissions.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/media_permissions.rs) | `commands::tests::analyze_frame_*` + `tools/lint-vision-doc/check.py` | Implemented |
| V2 | Frame data-URL validated before provider call (defense in depth in `maybe_apply_vision`) | [§1 step c](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/commands.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs) `validate_frame_data_url` | `commands::tests::frame_invalid_*` | Implemented |
| V3 | Ollama vision adapter with env-driven config (base URL, model, timeout) | [§2 Ollama](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md) | [`packages/l4-router/src/providers/ollama_vision.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l4-router/src/providers/ollama_vision.rs) | `cargo test -p aether-l4-router --features ollama-provider` + `tools/lint-vision-doc/` | Implemented |
| V4 | llama.cpp vision adapter, parallel surface to Ollama | [§2 llama.cpp](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md) | [`packages/l4-router/src/providers/llamacpp_vision.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l4-router/src/providers/llamacpp_vision.rs) | `cargo test -p aether-l4-router --features vision-llamacpp` | Implemented |
| V5 | `vision_provider.json` persistence: `model_per_provider` survives swap; unknown provider ids retained | [§3–§4](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/vision_registry.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/vision_registry.rs) | `vision_registry::tests::unknown_fields_are_dropped_on_rewrite`, `model_per_provider_survives_swap` | Implemented |
| V6 | TTL cache for model list (`AETHER_VISION_MODEL_TTL_SECS`, default 60 s, bounded `[5, 3600]`) | [§4 TTL cache](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/vision_cache.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/vision_cache.rs) `ModelListCache` | `vision_cache::tests::ttl_*` | Implemented |
| V7 | Image bytes transient at every layer — never in audit, durable memory, or telemetry | [§1 trailing rule](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md) | (negative requirement — `analyze_frame` never persists `frame_data_url`) | `tools/lint-vision-doc/check.py` ANCHORS | Implemented |

---

## 4. Voice V1 — push-to-talk single-utterance STT

Source: [`docs/VOICE-V1-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/VOICE-V1-ARCHITECTURE.md)

| # | Requirement | Source doc § | Implementation surface | Test / rot-guard | Status |
|---|-------------|--------------|------------------------|------------------|--------|
| Vo1 | Mic permission gate (Allow/Ask/Deny) consulted before capture | [§1](file:///C:/Users/dbhav/Projects/aether/docs/VOICE-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/mic_permissions.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/mic_permissions.rs) | `mic_permissions::tests::*` + `tools/lint-voice-doc/check.py` | Implemented |
| Vo2 | Push-to-talk single-utterance capture in `VoicePanel`; PCM 16 kHz mono WAV | [§1](file:///C:/Users/dbhav/Projects/aether/docs/VOICE-V1-ARCHITECTURE.md) | [`apps/desktop/src/components/VoicePanel.tsx`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/VoicePanel.tsx) | `ActiveVoiceRoute.test.tsx` | Implemented |
| Vo3 | whisper.cpp speech provider with env-driven config + healthcheck WARN | [§2](file:///C:/Users/dbhav/Projects/aether/docs/VOICE-V1-ARCHITECTURE.md) | [`packages/l4-router/src/providers/whispercpp_speech.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l4-router/src/providers/whispercpp_speech.rs) | `cargo test -p aether-l4-router --features speech-whispercpp` | Implemented |
| Vo4 | `voice_provider.json` parallel to vision; survives swaps | (parity table) | [`apps/desktop/src-tauri/src/voice_registry.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/voice_registry.rs) | `voice_registry::tests::*` | Implemented |
| Vo5 | No silent fallback on STT failure — surface visible error, never swallow utterance | [§1 divergence callout](file:///C:/Users/dbhav/Projects/aether/docs/VOICE-V1-ARCHITECTURE.md) | [`apps/desktop/src-tauri/src/commands.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs) `transcribe_utterance` (Err returned to UI) | `commands::tests::transcribe_failure_surfaces_error` | Implemented |
| Vo6 | Audio bytes transient at every layer | [§1 trailing rule](file:///C:/Users/dbhav/Projects/aether/docs/VOICE-V1-ARCHITECTURE.md) | (negative requirement) | `tools/lint-voice-doc/check.py` ANCHORS | Implemented |

---

## 5. Quality & Eval V1 — capture/replay + session-log importer + dry-run

Source: [`docs/QUALITY-EVAL-V1-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/QUALITY-EVAL-V1-ARCHITECTURE.md)

| # | Requirement | Source doc § | Implementation surface | Test / rot-guard | Status |
|---|-------------|--------------|------------------------|------------------|--------|
| Q1 | Three backends — `dry-run`, `ollama`, `replay` — selected via runner flags | [§3.1–§3.2](file:///C:/Users/dbhav/Projects/aether/docs/QUALITY-EVAL-V1-ARCHITECTURE.md) | [`tools/evals/__main__.py`](file:///C:/Users/dbhav/Projects/aether/tools/evals/__main__.py) `_resolve_actual` | [`tools/evals/test_capture_replay.py`](file:///C:/Users/dbhav/Projects/aether/tools/evals/test_capture_replay.py) | Implemented |
| Q2 | Capture writes `<id>.md` + `<id>.json` with `scenario_id / domain / backend / captured_at / prompt / response / metadata` | [§3.2](file:///C:/Users/dbhav/Projects/aether/docs/QUALITY-EVAL-V1-ARCHITECTURE.md) | [`tools/evals/__main__.py`](file:///C:/Users/dbhav/Projects/aether/tools/evals/__main__.py) `_write_capture_json`, `_capture_filename` | `test_capture_replay.py::test_capture_round_trip` + `tools/lint-quality-doc/check.py` | Implemented |
| Q3 | Live Ollama controlled by 3 env vars snapshotted together (`_ollama_env`) | [§3.2](file:///C:/Users/dbhav/Projects/aether/docs/QUALITY-EVAL-V1-ARCHITECTURE.md) | [`tools/evals/__main__.py`](file:///C:/Users/dbhav/Projects/aether/tools/evals/__main__.py) `_ollama_env`, `_ollama_generate` | `test_capture_replay.py` env-snapshot cases | Implemented |
| Q4 | Session-log importer ingests historical chat logs and stamps `backend = "session-log"` in capture metadata | [§3.1](file:///C:/Users/dbhav/Projects/aether/docs/QUALITY-EVAL-V1-ARCHITECTURE.md) | [`tools/evals/session_log_import.py`](file:///C:/Users/dbhav/Projects/aether/tools/evals/session_log_import.py) | [`tools/evals/test_session_log_import.py`](file:///C:/Users/dbhav/Projects/aether/tools/evals/test_session_log_import.py) | Implemented |
| Q5 | Open expectation DSL — unknown `kind` skipped, never a failure (additive) | [§2.1](file:///C:/Users/dbhav/Projects/aether/docs/QUALITY-EVAL-V1-ARCHITECTURE.md) | [`tools/evals/expectations.py`](file:///C:/Users/dbhav/Projects/aether/tools/evals/expectations.py) `EVALUATED_KINDS`, `evaluate_expectation` | `test_capture_replay.py::test_unknown_kind_is_skipped` | Implemented |
| Q6 | Markdown report grouped by domain, status badges per scenario | [§3.1](file:///C:/Users/dbhav/Projects/aether/docs/QUALITY-EVAL-V1-ARCHITECTURE.md) | [`tools/evals/report.py`](file:///C:/Users/dbhav/Projects/aether/tools/evals/report.py) `build_markdown_report` | `tools/lint-quality-doc/check.py` ANCHORS | Implemented |

---

## 6. Media permissions — three-state, per-kind persistence

Source: [`docs/MEDIA-PERMISSIONS.md`](file:///C:/Users/dbhav/Projects/aether/docs/MEDIA-PERMISSIONS.md)

| # | Requirement | Source doc § | Implementation surface | Test / rot-guard | Status |
|---|-------------|--------------|------------------------|------------------|--------|
| MP1 | Tri-state `allow / ask / deny` per device kind (`camera`, `screen`); default `ask` | Model + Persistence | [`apps/desktop/src-tauri/src/media_permissions.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/media_permissions.rs) `MediaPermissions`, `PermissionState`, `MediaKind` | `media_permissions::tests::default_is_ask` + `tools/lint-media-permissions-doc/check.py` | Implemented |
| MP2 | Atomic write-to-temp-then-rename; missing/malformed → `{ camera: ask, screen: ask }` (never `allow`) | Persistence | [`apps/desktop/src-tauri/src/media_permissions.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/media_permissions.rs) | `media_permissions::tests::malformed_falls_back_to_ask` | Implemented |
| MP3 | `evaluate_media_permission` returns `CaptureGate::{Proceed, PromptUser, Deny}`; consulted by every capture site | Enforcement | [`apps/desktop/src-tauri/src/state.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/state.rs), [`apps/desktop/src-tauri/src/commands.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs) | `commands::tests::analyze_frame_respects_deny` | Implemented |
| MP4 | Tauri capabilities allowlist is default-deny; `fs/shell/http/dialog/notification` deliberately absent | Tauri/webview model | [`apps/desktop/src-tauri/capabilities/default.json`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/capabilities/default.json) | `tools/lint-media-permissions-doc/check.py` | Implemented |
| MP5 | Screen-capture device wired in permission model but no capture surface yet | Model | [`apps/desktop/src-tauri/src/media_permissions.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/media_permissions.rs) (`MediaKind::Screen`), no `capture_screen` command | (no behavioural test — surface deferred) | Stub (deliberate per spec) |

---

## 7. Policy / L5 — autonomy preset, capability gate, audit chain

Source: [`packages/l5-policy/src/lib.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/lib.rs) (crate doc) + per-module headers; ADR-0009 for audit-row schema v2.

| # | Requirement | Source doc | Implementation surface | Test / rot-guard | Status |
|---|-------------|------------|------------------------|------------------|--------|
| L5.1 | Capability taxonomy — 7 groups + per-modality variants (Memory*, MediaCamera, MediaMic, MediaScreenCapture, RetrievalContext, Persona*) | [`packages/l5-policy/src/capability.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/capability.rs) header | [`packages/l5-policy/src/capability.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/capability.rs) `Capability` | `cargo test -p aether-l5-policy capability::` | Implemented |
| L5.2 | Autonomy preset overlay (`PresetId`) — preset switches via `policy.set_preset` | [`packages/l5-policy/src/posture.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/posture.rs) | [`packages/l5-policy/src/posture.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/posture.rs) `PolicyPostureSummary`, [`packages/l5-policy/src/engine.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/engine.rs) | `cargo test -p aether-l5-policy engine::preset_*` | Implemented |
| L5.3 | Append-only HMAC-chained `policy_audit_log`; one canonical chain | ADR-0016 §1 | [`packages/l5-policy/src/audit_seal.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit_seal.rs), [`packages/l5-policy/src/audit_store.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit_store.rs) | `cargo test -p aether-l5-policy audit_seal::*` + `tools/lint-policy-doc/check.py` | Implemented |
| L5.4 | All file I/O / network / subprocess gated through L5 (CLAUDE.md §1.5) | [`CLAUDE.md` §1.5](file:///C:/Users/dbhav/Projects/aether/CLAUDE.md) | [`packages/l5-policy/src/engine.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/engine.rs) | [`tools/lint-policy-bypass/`](file:///C:/Users/dbhav/Projects/aether/tools/lint-policy-bypass/) | Implemented |
| L5.5 | Grants surface — revoke-precedence; otherwise LWW by Lamport | ADR-0016 §2 | [`packages/l5-policy/src/grants.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/grants.rs) | `cargo test -p aether-l5-policy grants::*` | Implemented |
| L5.6 | TS mirrors of policy decisions are codegen, not hand-authored | [`CLAUDE.md` §4](file:///C:/Users/dbhav/Projects/aether/CLAUDE.md) | [`packages/l5-policy-ts/src/`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy-ts/src/) + [`tools/ts-bindings-gen/`](file:///C:/Users/dbhav/Projects/aether/tools/ts-bindings-gen/) | (build step + `tools/lint-layer-boundaries/`) | Implemented |

---

## 8. Persona delivery (ADR-0012)

Source: [`docs/adr/ADR-0012-persona-delivery-download-on-demand.md`](file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0012-persona-delivery-download-on-demand.md)

| # | Requirement | ADR § | Implementation surface | Test / rot-guard | Status |
|---|-------------|-------|------------------------|------------------|--------|
| PD1 | Tier 1 — bundled previews per persona (`preview.webp` + `preview_voice.opus` + `preview.yaml`), ≤130 KB each | §Decision Tier 1 | [`tools/build-persona-previews/build.py`](file:///C:/Users/dbhav/Projects/aether/tools/build-persona-previews/build.py), `apps/desktop/public/personas-previews/` | [`apps/desktop/src/lib/personaPreviews.test.ts`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/lib/personaPreviews.test.ts) | Implemented |
| PD2 | Tier 2 — full pack (~15 MB) downloaded on selection; only chosen persona's pack on disk | §Decision Tier 2 | [`tools/build-persona-pack/build.py`](file:///C:/Users/dbhav/Projects/aether/tools/build-persona-pack/build.py), [`apps/desktop/src-tauri/src/main.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/main.rs) `install_persona_via_http` + `install_persona_from_local_files` | `http_install_tests::install_persona_via_http_end_to_end`, `persona_install_orchestration_tests::*` | Implemented — HTTP fetch landed in `48f3765`; install orchestrator parameterized on injected pk + bundled real-key swap landed in `91f23a9` (T1.5 close 2026-04-30) |
| PD3 | Ed25519 manifest signature verify before extract | §Decision switch flow step 3 | [`packages/l6-persona/src/manifest_verifier.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l6-persona/src/manifest_verifier.rs); bundled `RELEASE_PUBLIC_KEY_B64` const at [`apps/desktop/src-tauri/src/main.rs:44`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/main.rs) | `manifest_verifier::tests::verify_round_trip`; `bundled_release_key_tests::*` (4 cases incl. `bundled_key_const_differs_from_fixture_pk`) | Implemented — bundled const is the real production pubkey as of T1.5 close (`91f23a9`, 2026-04-30); the seed-derived cross-language fixture remains separate by design for repeatable test signing |
| PD4 | SHA-256-checked atomic extract (zip → temp → rename) | §Decision switch flow step 4 | [`packages/l6-persona/src/install.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l6-persona/src/install.rs) `extract_pack_zip` | `install::tests::extract_unpacks_zip_and_atomic_renames_partial`, `extract_refuses_existing_install` | Implemented |
| PD5 | Atomic uninstall-then-install on switch; mid-switch failure leaves current persona intact | §Decision switch flow step 7 | [`packages/l6-persona/src/install.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l6-persona/src/install.rs), [`apps/desktop/src-tauri/src/commands.rs`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/commands.rs) | `install::tests::failure_during_extract_preserves_existing` | Implemented |
| PD6 | User memory persona-independent (switch never wipes `memory.db`) | §Decision user memory | (negative requirement — `memory_router` keyed by user, not persona) | `memory_router::tests::switch_persona_preserves_memory` | Implemented |
| PD7 | `Capability::PersonaDownload / PersonaInstall / PersonaUninstall / PersonaSwitch` gate every step | §Decision (implied via L5 §1.5) | [`packages/l5-policy/src/capability.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/capability.rs) | `cargo test -p aether-l5-policy capability::persona_*` | Implemented |
| PD8 | Onboarding wizard wires Tier-1 selection + first install | `docs/ONBOARDING-SPEC.md` | [`apps/desktop/src/components/PersonaWizard.tsx`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/PersonaWizard.tsx) | [`apps/desktop/src/components/PersonaWizard.test.tsx`](file:///C:/Users/dbhav/Projects/aether/apps/desktop/src/components/PersonaWizard.test.tsx) | Implemented |

---

## 9. Mobile sync (ADR-0016)

Source: [`docs/adr/ADR-0016-mobile-sync-schema.md`](file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0016-mobile-sync-schema.md)

ADR-0016 is design-only — empirical validation arrives when a real
mobile app exists. The rows below cover what landed in the
**desktop** schema reservation today.

| # | Requirement | ADR § | Implementation surface | Test / rot-guard | Status |
|---|-------------|-------|------------------------|------------------|--------|
| S1 | Schema additivity — every syncable mutable table grows by `device_id`, `origin_seq`, `logical_clock`, `last_modified_at`, `tombstoned`; existing single-device installs remain valid | §3 | [`packages/storage/src/migrations.rs`](file:///C:/Users/dbhav/Projects/aether/packages/storage/src/migrations.rs) | `migrations::tests::sync_columns_default_to_safe_values` (planned) | Stub — schema reservation, no sync engine |
| S2 | New metadata tables: `sync_devices`, `sync_state`, `sync_outbox`, `cost_counter_contributions` | §3 | [`packages/storage/src/migrations.rs`](file:///C:/Users/dbhav/Projects/aether/packages/storage/src/migrations.rs) | (covered by S1 test) | Stub |
| S3 | Per-domain conflict resolution rules — LWW for memory, tombstone-precedence, revoke-precedence for grants, PN-counter for cost, first-response-wins for approvals | §2 | [`tools/sync-schema-validator/engine.py`](file:///C:/Users/dbhav/Projects/aether/tools/sync-schema-validator/engine.py), [`tools/sync-schema-validator/validate.py`](file:///C:/Users/dbhav/Projects/aether/tools/sync-schema-validator/validate.py) | [`tools/sync-schema-validator/`](file:///C:/Users/dbhav/Projects/aether/tools/sync-schema-validator/) fixture-driven validator (synthetic event stream) | Implemented (validator green; engine itself is stub) |
| S4 | Audit chain has one canonical instance on desktop; mobile shard merges via wrapping records | §1 | [`packages/l5-policy/src/audit_seal.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l5-policy/src/audit_seal.rs) (chain shape exists; merge protocol does not) | (no test — protocol not yet implemented) | Stub — desktop-canonical chain present; mobile merge unwritten |
| S5 | Persona pack files do NOT sync; active-pointer does | §4 (and ADR-0012 §user memory) | [`packages/l6-persona/src/install.rs`](file:///C:/Users/dbhav/Projects/aether/packages/l6-persona/src/install.rs) (per-device install) | (negative requirement — no sync rule for `persona_packs`) | Implemented (by absence) |
| S6 | Identity / pairing — mDNS + long-lived TLS WebSocket, QR + numeric confirmation; off-LAN relay deferred | §5 | (no implementation; design only) | n/a | Stub (deliberate per ADR — empirical validation deferred) |
| S7 | PN-counter convergence for `cost_counters` keyed by `device_id` | §2 | [`tools/sync-schema-validator/engine.py`](file:///C:/Users/dbhav/Projects/aether/tools/sync-schema-validator/engine.py) (PN-counter rule) | `tools/sync-schema-validator/` PN-counter fixture | Implemented (validator only) |

---

## 10. Coverage notes

- **Total rows:** 50 (M1–M11 + P1–P8 + V1–V7 + Vo1–Vo6 + Q1–Q6 + MP1–MP5 + L5.1–L5.6 + PD1–PD8 + S1–S7).
- **Rows where status ≠ Implemented (highest-value findings):**
  - **M4** Retention sweep — Partial; Facts/Projects/Preferences/Artifacts deferred per ADR-0005.
  - **P6** macOS / Linux idle probes — Partial; only Windows `GetLastInputInfo` shipped.
  - **P7** Runtime renderer — Stub by design (the scaffold reserves the contract).
  - **MP5** Screen capture surface — Stub by design (permission model wired, no `capture_screen` command yet).
  - ~~**PD2** Tier-2 download — Partial~~ — **CLOSED 2026-04-30** in commit `91f23a9` (T1.5). HTTP fetch + real-key swap + parameterized verify all shipped.
  - ~~**PD3** Manifest signature — uses fixture key today~~ — **CLOSED 2026-04-30** alongside PD2. Bundled const is the real production pubkey; the seed-derived fixture is intentionally separate for test signing.
  - **S1 / S2 / S4 / S6** — design-only schema reservations per ADR-0016; sync engine itself is unwritten.
  - **S3 / S7** — validator implements the rules and runs green; the engine that consumes the rules in production is stub.
- **Rows excluded (intentionally):** doc-tone rules from `docs/AC-STYLE.md` (Gap #6 — separate doc), forward-looking requirement IDs (Gap #3), OSS/Pro/Cross-system spec views (Gap #4), NFRs (`docs/NFR.md` is its own surface).
- **Rot-guard vs AC reminder.** A row that cites only `tools/lint-*-doc/check.py` is doc/code-consistency-checked, not behaviourally tested. Per [`docs/GLOSSARY.md` §6](file:///C:/Users/dbhav/Projects/aether/docs/GLOSSARY.md), this is deliberate — rot guards prevent drift, behavioural tests prove behaviour. Both are listed where they exist.

---

## 11. How this matrix stays honest

- New ADRs add new rows here in the same PR.
- When a row's `Implementation surface` symbol is renamed or
  deleted, the rot guard for the same source doc fails — fix the
  row at the same time.
- `Status` upgrades from Stub → Partial → Implemented are part of
  the slice that lights them up; never edit Status alone.
- This file is hand-maintained. There is no generator. If a
  generator becomes worthwhile, it lives under `tools/build-rtm/`
  and writes back to this same path so external links don't break.

---

## 12. Reference

- [`docs/GLOSSARY.md`](file:///C:/Users/dbhav/Projects/aether/docs/GLOSSARY.md) — terminology baseline; especially §6 (rot guards != AC).
- [`docs/MEMORY-V2-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md), [`docs/PRESENCE-V1-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md), [`docs/VISION-V1-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/VISION-V1-ARCHITECTURE.md), [`docs/VOICE-V1-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/VOICE-V1-ARCHITECTURE.md), [`docs/QUALITY-EVAL-V1-ARCHITECTURE.md`](file:///C:/Users/dbhav/Projects/aether/docs/QUALITY-EVAL-V1-ARCHITECTURE.md), [`docs/MEDIA-PERMISSIONS.md`](file:///C:/Users/dbhav/Projects/aether/docs/MEDIA-PERMISSIONS.md) — the six locked architecture surfaces.
- [`docs/adr/`](file:///C:/Users/dbhav/Projects/aether/docs/adr/) — accepted decisions (ADR-0001 through ADR-0016).
- [`tools/`](file:///C:/Users/dbhav/Projects/aether/tools/) — rot guards (`lint-*-doc`) and validators (`sync-schema-validator`, `lint-policy-bypass`, `lint-layer-boundaries`).
