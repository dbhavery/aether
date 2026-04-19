---
status: working
date: 2026-04-18
owner: L6 interface pack
layer: L6 — Persona Compiler
source_of_truth: file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md
related:
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md
  - file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_L3_L6_integration_notes.md
---

# L6 — Persona Compiler Interface Pack

Distilled implementation-prep view of L6's boundary: the Persona Compiler as seen by L1/L2/L3/L4/L5/L7. Normative text lives in the system design; this pack collects the signatures, field sets, event names, and error vocabulary an implementer needs to stub against L6 before L6 ships.

---

## 1. Purpose

L6 is a deterministic **compiler** that ingests declarative persona inputs (packs, onboarding choices, user overrides, confirmed observed-style, and — for Don only — a privileged Isabelle overlay) and emits a single versioned `CompiledPersona` bundle with six typed sub-artifacts, one per consumer layer. It owns the persona lifecycle (load → validate → migrate → merge → verify → hot-reload) and nothing else.

Load-bearing invariants (from L6 §1.3, reinforced here):

- **I-1 (THE INVARIANT).** Persona proposes; L5 decides. No compiled field affects authorization before L5 evaluates under its precedence rule (`hardcoded-blocks > user-override > persona-default > preset-default > system-default`). L6 emits defaults only.
- **I-2.** Persona cannot bypass hardcoded blocks or privacy-posture gates — not even via the Isabelle overlay.
- **I-3.** Compilation is deterministic (byte-identical artifact for identical inputs).
- **I-5.** Acknowledgment pool and safety-deflection pool are structurally separate.
- **I-6.** Privileged overlay is opt-in, signed, locally resolved, build-time gated; never shipped in public distributables.
- **I-8.** No silent learning. Observed-style updates require explicit user confirmation in L7.

---

## 2. Primary responsibilities

L6 **owns**:

- Persona pack **schema validation** (every §3 rule + `17_persona_pack_schema.md §Validation`), including enum bounds, [0,1] scalars, pool-separation check (I-5), unknown-field preservation + warning.
- **Versioning + migration.** `schema_version` up-migrations (`migrate::v{N-1}_to_v{N}`); refuse load when pack is newer than compiler (`VersionMismatch`).
- **Compilation** to the six Compiled* artifacts (`CompiledLanguage`, `CompiledSalience`, `CompiledVisual`, `CompiledRouting`, `CompiledPolicyDefaults`, `PersonaSummary`) — bundled into one `CompiledPersona` emitted as `compiled_persona_ready`.
- **Hot-reload state machine** (`IDLE → COMPILING → STAGED → SWAP_BEGIN → SWAP_COMMIT → ACTIVE`; rollback on NACK/timeout) with L1 safe-boundary coordination.
- **Signature verification** (Ed25519 against pinned keys); drives `provenance_status` (`Trusted | Unverified | PrivilegedOverlay`); unsigned packs clamped to `ask` on any would-widen approval override and tagged untrusted-context for L4.
- **Privileged-overlay resolution** (Isabelle only). Build-time feature flag `privileged-overlay` + `--profile=isabelle` gating; signature required; refuses silently to downgrade — either loads as privileged or strips the flag with audit trail.
- **Observed-style proposal pipeline** (§13). Bounded emitter set; proposes via `persona_observed_style_proposed`; only applies after L7 confirmation; decays unconfirmed proposals.
- Emission of `compiled_persona_ready`, `persona_swap_begin/commit/rollback`, `persona_compile_failed`, `persona_observed_style_proposed` on the event bus.
- **MinimumTrust** baked-in fallback persona (compile-time constant, not a pack).

L6 **does NOT own**:

- **Authorization.** That is L5's decision under §6.3 precedence. L6 emits defaults; L5 composes.
- **Turn state / safe-boundary definition.** L1 owns and signals; L6 waits.
- **Routing execution / tier clamping.** L4 consumes `CompiledRouting`; L4 makes the call.
- **Memory retrieval.** L2 uses `CompiledSalience` to rank; L6 does not retrieve or gate.
- **Presence animation / intensity clamping at render.** L3 consumes `CompiledVisual`; L3 schedules behaviors.
- **Persona authoring tooling** (pack scaffold CLI, inpainter, landmark extractor) — separate package.
- **Prompt templating at runtime** (the `system_prompt` is an authored literal; no Jinja).
- **Personality inference.** The compiler does not watch the user; observed-style is a user-confirmed channel only.

---

## 3. Inbound interfaces

Six typed sources, ordered lowest-trust → highest (L6 §2):

| # | Source | Shape | Ownership / Path |
|---|---|---|---|
| 1 | **Persona pack files** | YAML (`persona.yaml`, `voice.yaml`, `metadata.yaml`) + assets per `17_persona_pack_schema.md` | Filesystem under `<install>/personas/<id>/`; read via typed adapter (never free-form YAML into the compiler) |
| 2 | **Onboarding choices** | Wizard answers (persona selection, style axes, preset recommendation acceptance) | From L7 via `onboarding.step_saved` event; persisted in user profile store |
| 3 | **User-settings overrides** | `UserOverrides { identity_axes, visual_bounds, language_selection, routing_prefs, approval_mode_overrides }` | From L7 via `persona.user_override_set`; overrides touching `approval_mode_overrides` are L5-gated |
| 4 | **Observed-style signals (user-confirmed only)** | `ConfirmedStyleEntry { field_path, value, evidence_ref, confirmed_at }` | Confirmed-overrides journal, persona-scoped; appended only after L7 confirm |
| 5 | **Privileged-profile overlay** (Isabelle) | Signed Ed25519 pack at `file:///C:/Users/dbhav/.aether/overlays/isabelle/` (default; env-configurable via `AETHER_PRIVILEGED_OVERLAY_PATH`) | Don's private path; never referenced from public files; loaded only when `privileged-overlay` build feature is on AND signature verifies |
| 6 | **Core health tier** | `core.health.tier_changed { tier: Lite \| Balanced \| Full }` | Core; triggers recompile only when tier-clamped fields would materially change |

Subscribed events (compiler reactions):

- `onboarding.step_saved` → stage inputs; mark dirty.
- `persona.user_override_set` → stage override; mark dirty.
- `persona.observed_style_confirmed` → append to journal; mark dirty.
- `policy_decision` (L5) → diagnostics only; never auto-adjusts persona.
- `core.health.tier_changed` → re-emit `CompiledRouting` / `CompiledLanguage` / `CompiledVisual` if tier-clamped values change.

---

## 4. Outbound interfaces

One bundled event (`compiled_persona_ready`) carrying the six sub-artifacts; lifecycle events for the hot-reload state machine; observed-style proposal; compile-fail surface.

### 4.1 Compiled artifacts → consumer layers

| Consumer | Artifact | Contract field summary |
|---|---|---|
| L1 | `CompiledLanguage` | `phrase_pool`, `acknowledgment_pool`, `deflection_pool` (SEPARATE — I-5), `clarification_pool`, `ack_style { warmth, brevity, formality, filler_density }`, `initiative_bias`, `hardcoded_allowed_deflections`, `pool_version` |
| L2 | `CompiledSalience` | `salience_rules: Vec<SalienceRule>`, `retention_bias`, `isolation`, `retention_days`, `persona_can_forget`, `persona_scoped_rng_seed` |
| L3 | `CompiledVisual` | `avatar_pack_ref`, `visual_params { target_fps, idle_blink_rate_hz, idle_micro_movement_scale, presence { gaze_warmth, smile_baseline, listening_lean_strength } }`, `intensity_bounds`, `gaze_style`, `anti_uncanny_settings`, `state_clip_manifest_ref` |
| L4 | `CompiledRouting` | `tier_preference` (perf tier: Lite/Balanced/Full), `llm_preferences { preferred_tier (model tier: fast/main/heavy), temperature, max_output_tokens, pinned_model? }`, `privacy_posture`, `cost_preference`, `provider_pins?`, `remote_bias`, `safety_header` |
| L5 | `CompiledPolicyDefaults` | `preset_recommendation`, `approval_mode_overrides: HashMap<Capability, ApprovalMode>`, `privacy_posture`, `privileged_profile` — **defaults only; L5 composes under §6.3 precedence** |
| L7 | `PersonaSummary` | `persona_id, display_name, tagline, description, archetype, avatar_preview_ref, sample_wav_ref, default_preset_recommendation, provenance_status, license_summary_ref, version, privileged_profile` |

### 4.2 Events emitted on the Rust event bus

| Event | Payload | Consumers |
|---|---|---|
| `compiled_persona_ready` | `persona_id, version, change_id, compiled_at, artifact_ref, provenance_status` | L1, L2, L3, L4, L5, L7 |
| `persona_swap_begin` | `persona_id, previous_id, change_id, compile_time_ms` | L1, L2, L3, L4, L5, L7 |
| `persona_swap_commit` | `persona_id, change_id` | L1, L2, L3, L4, L5, L7 |
| `persona_swap_rollback` | `persona_id, reason, change_id` | L1, L2, L3, L4, L5, L7 |
| `persona_compile_failed` | `persona_id, version, reason, change_id` | L7 (banner), L5 (audit) |
| `persona_observed_style_proposed` | `persona_id, field_path, proposed_value, evidence_ref, proposal_id` | L7 (confirmation UI), L5 (audit) |

### 4.3 Tauri IPC surface (per L6 §10, aligned with `X3 §2.2`)

`persona.list`, `persona.get`, `persona.compile`, `persona.hot_reload`, `persona.validate`, `persona.authoring.preview`, `persona.set_user_overrides` (L5-gated when touching `approval_mode_overrides`), `persona.export` (L5-gated, re-auth), `persona.observed_style.confirm`, `persona.observed_style.reject`.

---

## 5. Synchronous vs asynchronous boundaries

| Surface | Mode | Notes |
|---|---|---|
| `persona.validate(pack)` | **synchronous** | Pure inspection; returns `ValidationReport` with no state change |
| `persona.compile(id)` | **sync-returns** `CompiledPersonaHandle` | Pipeline runs inline (may be long for large pools); result is *staged*, not yet active |
| `persona.hot_reload(handle)` | **asynchronous, two-phase** | `SWAP_BEGIN` fires → waits for L1 safe-boundary ack → `SWAP_COMMIT` + `compiled_persona_ready`; on NACK or 500 ms timeout → `SWAP_ROLLBACK`; ACTIVE persona never in partial state |
| Safe-boundary wait | **async** | L1 owns signal (Idle / end-of-Speaking / end-of-AcknowledgingWait); strictness is Open Q #1 |
| Signature verify | **sync** within compile stage 11 | Failure either refuses (privileged) or demotes to `Unverified` (non-privileged) |
| Migration | **sync** within compile stage 3 | Up-migration only; failure → `MigrationFailed` and refuse load |
| Observed-style confirm | **async** | L7 fires `persona.observed_style.confirm` → journal append → dirty → recompile on next safe boundary |

The commit phase is **gated on L1 safe-boundary ack** — L6 never commits mid-utterance.

---

## 6. Typed contract suggestions

All names are pseudo-Rust; exact derives, lifetimes, and error nesting deferred to implementation.

### 6.1 Trait

```
trait PersonaCompiler {
    fn list(&self) -> Vec<PersonaSummary>;
    fn get(&self, id: PersonaId) -> Result<PersonaSummary, PersonaError>;
    fn compile(&self, id: PersonaId) -> Result<CompiledPersonaHandle, PersonaError>;
    fn hot_reload(&self, handle: CompiledPersonaHandle) -> Result<ChangeId, PersonaError>;
    fn validate(&self, pack: PersonaPackRef) -> ValidationReport;
    fn subscribe(&self, filter: PersonaEventFilter) -> EventStream<PersonaEvent>;
    fn set_user_overrides(&self, id: PersonaId, ov: UserOverrides) -> Result<ChangeId, PersonaError>;
    fn export(&self, id: PersonaId) -> Result<Uri, PersonaError>; // L5-gated
}
```

### 6.2 Bundle

```
struct CompiledPersona {
    persona_id:         PersonaId,
    version:            SemVer,
    schema_version:     u32,
    change_id:          ChangeId,
    compiled_at:        MonotonicTimestamp,
    provenance_status:  ProvenanceStatus,  // Trusted | Unverified | PrivilegedOverlay
    language:           CompiledLanguage,
    salience:           CompiledSalience,
    visual:             CompiledVisual,
    routing:            CompiledRouting,
    policy_defaults:    CompiledPolicyDefaults,
    summary:            PersonaSummary,
}
```

### 6.3 Sub-artifacts

```
struct CompiledLanguage {
    phrase_pool:                  AckPhrasePool,
    acknowledgment_pool:          AckPhrasePool,   // alias for phrase_pool (L1 consumes as phrase_pool)
    deflection_pool:              AckPhrasePool,   // kind: Safety — SEPARATE (I-5)
    clarification_pool:           AckPhrasePool,
    ack_style:                    AckStyle,        // { warmth, brevity, formality, filler_density: f32 in 0..1 }
    initiative_bias:              f32,             // 0..1
    hardcoded_allowed_deflections: Vec<PhraseId>,
    pool_version:                 u32,
}

struct CompiledSalience {
    salience_rules:        Vec<SalienceRule>,      // match (domain? | privacy_class? | recency_bucket? | tags?) → weight: f32
    retention_bias:        RetentionBias,          // Lean | Balanced | Retentive
    isolation:             bool,
    retention_days:        u32,
    persona_can_forget:    bool,
    persona_scoped_rng_seed: u64,
}

struct CompiledVisual {
    avatar_pack_ref:        AssetRef,
    visual_params:          VisualParams,          // target_fps, idle_blink_rate_hz, idle_micro_movement_scale, presence{...}
    intensity_bounds:       IntensityBounds,
    gaze_style:             GazeStyle,             // Attentive | Reserved | Playful | Neutral
    anti_uncanny_settings:  AntiUncannySettings,
    state_clip_manifest_ref: AssetRef,
}

struct CompiledRouting {
    tier_preference:    PerfTierPreference,        // Lite | Balanced | Full  (from core.health)
    llm_preferences:    LlmPreferences,            // { preferred_tier: ModelTier (fast|main|heavy), temperature, max_output_tokens, pinned_model? }
    privacy_posture:    PrivacyPosture,            // Strict | Standard | Permissive
    cost_preference:    CostPreference,            // Low | Balanced | QualityFirst
    provider_pins:      Option<ProviderPins>,      // P2+; requires grant
    remote_bias:        f32,
    safety_header:      String,                    // compiled preamble (L4 §types.104)
}

struct CompiledPolicyDefaults {
    preset_recommendation:     PresetId,
    approval_mode_overrides:   HashMap<Capability, ApprovalMode>, // DEFAULTS ONLY (I-1)
    privacy_posture:           PrivacyPosture,
    privileged_profile:        bool,
}

struct PersonaSummary {
    persona_id:                     PersonaId,
    display_name:                   String,
    tagline:                        String,         // ≤120 chars
    description:                    String,
    archetype:                      Archetype,      // 17 §Archetype catalog
    avatar_preview_ref:             AssetRef,
    sample_wav_ref:                 AssetRef,
    default_preset_recommendation:  PresetId,
    provenance_status:              ProvenanceStatus,
    license_summary_ref:            AssetRef,
    version:                        SemVer,
    privileged_profile:             bool,           // L7 hides entirely unless Don's profile
}
```

### 6.4 Schema root (authoring side)

```
struct PersonaPack {
    persona: PersonaRoot,          // identity, identity_params, language, memory_salience_rules,
                                   // routing_prefs, visual, policy_defaults, provenance
    _unknown: HashMap<String, Value>,  // preserved, warned — never silently dropped
}
```

### 6.5 Validation

```
struct ValidationReport {
    ok:        bool,
    errors:    Vec<ValidationError>,   // field_path, rule, detail
    warnings:  Vec<ValidationWarning>, // unknown-field preservations, missing-optional defaults
    pack_ref:  PersonaPackRef,
}
```

---

## 7. Error vocabulary

```
enum PersonaError {
    InvalidSchema { field_path: String, rule: String, detail: String },
    VersionMismatch { pack_schema: u32, compiler_schema: u32 },
    SignatureFailed { pack_id: PersonaId, reason: SignatureFailReason },
    UnsignedPrivilegedOverlay { overlay_path: Uri },
    MigrationFailed { from: u32, to: u32, cause: String },
    CompileException { stage: CompileStage, cause: String },
    SafeBoundaryTimeout { change_id: ChangeId, waited_ms: u32 },
}
```

Event-surface analogs: `persona_compile_failed { reason }` carries a projected form of `PersonaError` for L7 banner rendering and L5 audit.

---

## 8. Dependency expectations

| Dependency | Purpose | Notes |
|---|---|---|
| **Pack storage** | Read persona packs from `<install>/personas/<id>/` and the privileged overlay path | Typed adapter only; no free-form YAML outside it. Quarantine path `personas/_quarantine/<id>/` on corruption |
| **Keyring / keystore** | Pinned Ed25519 verification keys: first-party and (on `--profile=isabelle` only) Don's privileged key | Public builds MUST NOT embed Don's key (build-time lint + manifest diff gate) |
| **L1 safe-boundary signals** | Coordinate `SWAP_BEGIN → SWAP_COMMIT` | 500 ms timeout per L6_plan Risk 2 |
| **Rust event bus** (`X3 §5`) | Emit all §4.2 events; subscribe to L5/L7/Core feeds | One channel; all consumer layers subscribe |
| **User profile store** | Persist onboarding answers, user overrides, confirmed-overrides journal | Persona-scoped |
| **L5** | Audits every compile, swap, override-set, observed-style transition; gates `set_user_overrides` (when approval overrides) and `export`; composes `CompiledPolicyDefaults` under precedence | Consumes — never compiles |
| **L7** | Onboarding, settings, observed-style confirmation UI, picker (uses `PersonaSummary`) | Consumes — never compiles |
| **L2 / L3 / L4** | Pure consumers of `CompiledSalience` / `CompiledVisual` / `CompiledRouting` via `compiled_persona_ready` handle | No re-parse of YAML anywhere outside L6 |

**Consumer rule.** L1/L2/L3/L4/L5/L7 subscribe; none of them compile personas. The YAML → typed path exists exactly once in the codebase, in L6.

---

## 9. Implementation notes

Per monorepo layout (§2 of monorepo plan), two packages:

- **`packages/l6-persona`** (Rust core + compiler) — owns schema adapters, validator, migration chain, compiler pipeline (stages 1–13 per L6 §5.1), signature verifier, hot-reload state machine, privileged-overlay resolver, observed-style journal, event emission, MinimumTrust baked-in fallback.
- **`packages/l6-persona-ts`** (TS types via `ts-rs`, per L6 §18 Q2 recommendation) — auto-generated bindings so L7's picker, onboarding, and trust center consume the same types L6 emits. Also houses the non-compile authoring helpers (`persona.validate`, `persona.authoring.preview`) per `X3 §171`.

Asset locations:

- First-party public packs → `file:///C:/Users/dbhav/Projects/<repo>/personas/` (ship with build; Lite 2–3 packs, Pro 6–8).
- Privileged Isabelle overlay → `file:///C:/Users/dbhav/.aether/overlays/isabelle/` (outside the repo; never referenced from public files; gated by `privileged-overlay` cargo feature and `--profile=isabelle`).

Build-time guards:

- `privileged-overlay` cargo feature OFF by default; public and Pro builds cannot enable it.
- Manifest diff gate at release: Isabelle asset names deny-listed in OSS Preview + Pro public manifests.
- Don's Ed25519 public key embedded only on the `isabelle` build profile.

Stubs (§14 of design) unblock every sibling layer:

- `l6-persona-stub` Rust crate with `aurora_default` fixture + scripted swap/fail injection.
- TS bindings auto-generated; event fixtures as JSON golden files for L1/L4/L5/L7 tests.

---

## 10. Open questions (carried forward, not resolved)

Full list in L6 §18. Flagged here because they affect L6's interface shape directly:

1. **Safe-boundary strictness** (Strict = Idle-only vs Relaxed = end-of-utterance). L1 §1012 Q7 / L6 §18 Q1. Compiler supports both via `hot_reload.boundary_strictness`. Don locks.
2. **`tier_preference` terminology overload.** `17_*` uses it for model tier (fast|main|heavy); `L4 §87` uses it for perf tier (Lite|Balanced|Full). Compiler emits both under distinct names (`tier_preference` for perf tier, `llm_preferences.preferred_tier` for model tier). Recommend renaming persona field to `model_tier_preference` in schema v2.
3. **First-party signing scheme.** Ed25519 + pinned key in build vs OS-keychain-managed. Current recommendation: Ed25519 + pinned; revisit at X3 signed-updater design.
4. **Privileged-overlay path mechanism.** `AETHER_PRIVILEGED_OVERLAY_PATH` env var vs a signed manifest entry. Current choice: env var; flagged for X3 revisit.
5. **Observed-style confirmation UI.** L6 emits `persona_observed_style_proposed`; L7 UI flow not yet designed. Blocks I-8's user-facing half.

---

## 11. Cross-references

- file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L3_presence_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_L3_L6_integration_notes.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md
