---
status: working
date: 2026-04-18
owner: L6 agent (persona compiler system design)
layer: L6 — Persona / Compiler System
depends_on:
  - plans/L5_policy_engine_system_design.md
  - plans/L1_interaction_timing_system_design.md
  - plans/L4_model_router_system_design.md
  - plans/L7_trust_ux_onboarding_system_design.md
  - plans/X3_tauri_architecture.md
  - 17_persona_pack_schema.md
  - plans/L6_persona_engine.md
  - plans/00_ORCHESTRATION_MAP.md
depended_on_by:
  - plans/L1_interaction_timing_system_design.md
  - plans/L2_memory_kernel_system_design.md (sibling wave)
  - plans/L3_presence_engine_system_design.md (sibling wave)
  - plans/L4_model_router_system_design.md
  - plans/L5_policy_engine_system_design.md
  - plans/L7_trust_ux_onboarding_system_design.md
---

# L6 — Persona / Compiler System Design

Implementation-grade design for the L6 **Persona Compiler** — the subsystem that turns persona packs, onboarding choices, user settings and (for Don) the Isabelle privileged overlay into typed, versioned, deterministic runtime artifacts consumed by L1/L2/L3/L4/L5/L7.

This document freezes the cross-layer contracts, the schema, the hot-reload state machine, the failure modes, and the IPC surface so every other layer can stub against L6 before L6 ships.

Canonical source files:
- file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether-planning/MASTER_OUTLINE_TREE.md
- file:///C:/Users/dbhav/Projects/aether-planning/17_persona_pack_schema.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_engine.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md

---

## 1. Purpose and design stance

### 1.1 What L6 is

L6 is a **compiler**. It takes declarative inputs (persona packs, onboarding answers, user overrides, privileged overlay) and emits typed, versioned runtime artifacts — one named sub-struct per consumer layer. Those artifacts flow through the Rust event bus (see `X3 §5`) to L1/L2/L3/L4/L5/L7.

### 1.2 What L6 is not

- **Not a prompt template.** The persona `system_prompt` is a literal string authored by a human (per `L6_persona_engine.md §Borrowable-vs-custom`). There is no Jinja-style runtime templating in P0–P3. Hidden templating is a red-team and drift risk.
- **Not a decision-maker.** L6 emits *defaults*. L5 owns decisions. Persona cannot widen trust — it can only *recommend* defaults that L5 may compose per the §6.3 precedence rule.
- **Not an authoring tool.** The pack scaffold CLI, inpaint pipeline and landmark extractor live in a separate tooling package (`17 §generation pipeline`). The compiler reads the finished artifact; it does not produce it.
- **Not a personality inference engine.** L6 does not watch the user and "learn" tone. Observed-style signals follow §13's user-confirmed channel — never silent.

### 1.3 Design invariants (load-bearing)

These are stated up-front and referenced from every subsequent section:

- **I-1. Persona proposes; L5 decides.** Every policy-affecting field produced by L6 is a *default*, evaluated by L5 under the precedence rule `hardcoded-blocks > user-override > persona-default > preset-default > system-default` (L5 §6.3).
- **I-2. Persona cannot bypass hardcoded blocks or privacy-posture rules.** Not even the Isabelle overlay.
- **I-3. Compilation is deterministic.** Same inputs, same artifact, byte-identical. Enables replay and audit (L6 plan §Acceptance criteria, golden-file stability).
- **I-4. Every runtime-affecting field is validated.** Unknown fields are preserved and warned; required fields missing → compile refused.
- **I-5. The safety-deflection pool is separate from the acknowledgment pool.** Never mixed. Enforced at compile time (L1 §8.4).
- **I-6. Privileged overlay is opt-in, signed, and locally resolved.** It never ships in public distributables (build-time lint, §7).
- **I-7. Version mismatch is surfaced, not silenced.** Older-schema packs run migrations; newer-than-compiler packs refuse to load.
- **I-8. No silent learning.** Observed-style updates require explicit user confirmation in L7 (§13).

---

## 2. Input sources

L6 ingests from six typed sources, ordered lowest-trust → highest:

| # | Source | Ownership | Trust shape | Where it lives |
|---|---|---|---|---|
| 1 | **System defaults** | shipped with build | fully trusted | Rust static `SystemPersonaDefaults` |
| 2 | **Persona pack files** (YAML + assets per `17_*`) | first-party packs signed; community packs unsigned | `Trusted` if signature verifies against pinned key; else `Unverified` | `<install>/personas/<id>/` (Lite ships 2–3 packs, Pro ships 6–8) |
| 3 | **Onboarding wizard answers** (L7 §4 Screen 3, 5, 7) | L7 captures and persists | trusted after re-auth where required | User profile store |
| 4 | **User settings / manual overrides** | L7 settings UI | trusted | User profile store, scoped per persona |
| 5 | **Observed style suggestions** (confirmed only) | L6 proposes, L7 confirms, L5 audits | trusted only after confirmation | Confirmed-overrides journal, persona-scoped |
| 6 | **Privileged-profile overlay** (Isabelle) | Don's private path, signed | trusted only when signature matches Don's key **and** profile flag is set at build time | file:///C:/Users/dbhav/.aether/overlays/isabelle/ (example path; actual path Don-configured) |

Each source is ingested through a typed adapter; the compiler never reads free-form YAML outside these adapters.

**Contradiction flag.** The prompt allows "observed style preferences … never silent learning." `17_persona_pack_schema.md` has no field for observed-style state; it lives exclusively in the confirmed-overrides journal (§13). Not a contradiction — a boundary — but recorded here explicitly.

---

## 3. Persona model — conceptual schema (pseudo-YAML)

This is the *authoring* schema as the compiler reads it. It is an extension of `17_persona_pack_schema.md` — everything in 17 is retained; the fields below add the runtime-parameterization surface this system design demands.

> **Schema precedence.** Where this §3 adds a field not yet in `17_*`, it is an additive change targeting `17_* schema_version: 2`. Schema v1 packs continue to load via migration (§12); missing v2 fields receive validated defaults. Nothing in v1 is removed (per `17 §Future-proofing`).

```yaml
persona:
  # --- identity / stable keys ---
  id: aurora                         # REQUIRED, stable. Must match folder name (17 validator).
  schema_version: 2                  # REQUIRED. 1 accepted via migration.
  version: "1.4.0"                   # REQUIRED, semver. Persona content version.
  display_name: "Aurora"             # REQUIRED
  description: "Warm, grounded, calm presence for focused work."
  tagline: "<=120 chars"             # REQUIRED (17)
  avatar_asset_ref: "avatar/portrait.png"   # REQUIRED (17)

  # --- identity / relationship parameters ---
  identity:
    relationship_mode: assistant     # assistant | companion | colleague | mentor | guest
    warmth: 0.7                      # 0..1
    formality: 0.3                   # 0..1
    initiative: 0.4                  # 0..1 ; how often persona volunteers suggestions
    autonomy_posture: assistant      # observer | assistant | operator | power_user | custom_ref
                                     # RECOMMENDATION only — L5 preset is authoritative (I-1)
    memory_style: balanced           # lean | balanced | retentive
    expressiveness: 0.6              # 0..1
    boundaries:                      # deflection categories persona refuses to engage with
      - medical_diagnosis
      - financial_advice_specific
      - legal_advice_specific

  # --- language ---
  language:
    tone_descriptors: [warm, grounded, precise]
    preferred_phrasing_axes:
      directness: 0.6
      hedging: 0.2
      humor: 0.3
    phrase_pool_ref: "language/acknowledgments.yaml"   # or inline: list
    acknowledgment_pool_ref: "language/acknowledgments.yaml"
    safety_deflection_pool_ref: "language/safety_deflections.yaml"
      # SEPARATE file. Enforced at compile time. See I-5, L1 §8.4.
    clarification_pool_ref: "language/clarifications.yaml"

  # --- memory salience ---
  memory_salience_rules:
    # list of salience weight expressions; compiled into typed weight functions (§4 CompiledSalience)
    - match: { domain: work_project }
      weight: 1.2
    - match: { privacy_class: private }
      weight: 1.5
      retention_bias: retentive
    - match: { recency_bucket: last_7_days }
      weight: 1.1
    # Wildcard fall-through
    - match: { any: true }
      weight: 1.0

  # --- routing preferences (feed L4) ---
  routing_prefs:
    tier_preference: main            # Lite | Balanced | Full | fast | main | heavy
                                     # Lite/Balanced/Full = perf tier; fast/main/heavy = model tier (L4).
                                     # See §4.4 mapping.
    privacy_posture: standard        # strict | standard | permissive
    cost_preference: balanced        # low | balanced | quality_first
    provider_pins:                   # OPTIONAL, P2+; L5-gated
      main: null                     # e.g. "anthropic:claude-opus-4-7"
      heavy: null

  # --- visual (feed L3) ---
  visual:
    avatar_pack_ref: "avatar/"
    intensity_bounds:
      idle_micro_movement_scale: [0.2, 0.8]
      smile_baseline: [0.1, 0.5]
      gaze_warmth: [0.3, 0.9]
    gaze_style: attentive            # attentive | reserved | playful | neutral
    anti_uncanny_settings:
      blink_jitter_ms: 120
      micro_saccade_amplitude: 0.3
      max_held_expression_s: 2.5

  # --- policy defaults (feed L5) ---
  policy_defaults:
    preset_ref: Assistant            # L5 preset recommendation (L5 §6.4). RECOMMENDATION only (I-1).
    approval_mode_overrides:
      # capability -> mode. These are DEFAULTS; L5 composes under precedence (L5 §6.3).
      FilesRead: auto
      FilesWrite: ask
      BrowserOpen: task
      EmailSend: deny
    privileged_profile: false        # true only for the Isabelle overlay; audited by L5
    note: |
      Everything in policy_defaults is a DEFAULT.
      L5 final decision is authoritative.
      Precedence: hardcoded-blocks > user-override > persona-default > preset-default > system-default.

  # --- provenance ---
  provenance:
    author: "Don Havery"
    created: "2026-04-17"
    last_updated: "2026-04-18"
    signature:                        # present on first-party / privileged packs
      scheme: ed25519
      key_id: "aether-first-party-2026"
      signature_b64: "…"
    license: "custom_aether"
    assets_metadata_ref: "metadata.yaml"   # 17 metadata file
```

**Validation obligations (loader-enforced, in addition to `17 §Validation rules`):**

- Every enum value (`relationship_mode`, `autonomy_posture`, `memory_style`, `tier_preference`, `privacy_posture`, `cost_preference`, `gaze_style`, every approval mode) validated against a typed enum.
- Every scalar in `[0, 1]` bounded-checked.
- `phrase_pool_ref` ≠ `safety_deflection_pool_ref` (I-5).
- `policy_defaults.approval_mode_overrides` keys must be known `Capability` variants; unknown keys → warn + drop.
- `policy_defaults.privileged_profile = true` requires signature from Don's pinned key AND build-time profile flag (§7).
- Unknown top-level fields preserved and warned; unknown nested fields warned; never silently dropped.
- Schema version ≤ compiler schema version; otherwise refuse load (I-7).

---

## 4. Compiled outputs — what L6 emits to each layer

One `CompiledPersona` artifact, with named sub-structs (pseudotypes):

```
CompiledPersona {
  persona_id: PersonaId
  version: SemVer
  schema_version: u32
  change_id: ChangeId                  // set by write path; confirmed by compiled_persona_ready
  compiled_at: MonotonicTimestamp
  provenance_status: Trusted | Unverified | PrivilegedOverlay
  language: CompiledLanguage
  salience: CompiledSalience
  visual: CompiledVisual
  routing: CompiledRouting
  policy_defaults: CompiledPolicyDefaults
  summary: PersonaSummary              // L7 view
}
```

### 4.1 → L1 (interaction timing)

Confirmed against `L1 §7.5 "To L6 — persona consumption"`:

```
CompiledLanguage {
  phrase_pool: AckPhrasePool                      // per L1 §8.1 AckPhrasePool structure
  acknowledgment_pool: AckPhrasePool              // alias; L1 consumes as `phrase_pool`
  deflection_pool: AckPhrasePool { kind: Safety } // SEPARATE (I-5, L1 §8.4)
  clarification_pool: AckPhrasePool
  ack_style: AckStyle {
    warmth, brevity, formality, filler_density   // all 0..1
  }
  initiative_bias: f32                            // 0..1 ; feeds L1 volunteered-suggestion cadence
  hardcoded_allowed_deflections: Vec<PhraseId>    // used in L1 DegradedNoPolicy (L1 §7.5)
  pool_version: u32                               // bumps on recompile (L1 §8.1)
}
```

### 4.2 → L2 (memory kernel)

```
CompiledSalience {
  salience_rules: Vec<SalienceRule>
    // each rule: match (domain? | privacy_class? | recency_bucket? | tags?) → weight: f32
  retention_bias: Lean | Balanced | Retentive
  isolation: bool                                  // from 17 persona.memory.isolation
  retention_days: u32                              // from 17 persona.memory.retention_days
  persona_can_forget: bool                         // from 17
  persona_scoped_rng_seed: u64                     // for L2 reproducibility (L6 plan §Open decisions)
}
```

### 4.3 → L3 (presence engine)

```
CompiledVisual {
  avatar_pack_ref: AssetRef
  visual_params: {
    target_fps: u16                                // may be tier-overridden by L3
    idle_blink_rate_hz: f32
    idle_micro_movement_scale: f32
    presence: { gaze_warmth, smile_baseline, listening_lean_strength }
  }
  intensity_bounds: IntensityBounds                // clamped ranges (§3 visual.intensity_bounds)
  gaze_style: GazeStyle
  anti_uncanny_settings: AntiUncannySettings
  state_clip_manifest_ref: AssetRef                // 17 avatar/clips/manifest.json
}
```

### 4.4 → L4 (model router)

Confirmed against `L4 §types.104`:

```
CompiledRouting {
  tier_preference: PerfTierPreference              // Lite | Balanced | Full  (core.health tier)
  llm_preferences: {                               // L4 consumes these directly
    preferred_tier: ModelTier                      // fast | main | heavy
    temperature: f32
    max_output_tokens: u32
    pinned_model: Option<ProviderId+ModelId>       // P2+; L5-gated
  }
  privacy_posture: PrivacyPosture                  // Strict | Standard/Balanced | Permissive/Open
  cost_preference: CostPreference                  // Low | Balanced | QualityFirst
  provider_pins: Option<ProviderPins>              // P2+; requires grant
  remote_bias: f32                                 // derived from cost_preference + tier_preference
  safety_header: String                            // compiled preamble (L4 §types.104)
}
```

> **Terminology reconciliation (flagged).** `17_*` uses `preferred_tier: fast|main|heavy` (model tier). `L4 §87` uses `tier_preference: Lite|Balanced|Full` (core-health perf tier). Both exist, both are consumed. The compiler emits both — `tier_preference` from performance tier detection, `llm_preferences.preferred_tier` from the persona. Routing decisions combine them per `L4 §4–5`. No doctrinal conflict, but the naming is easy to confuse; surfaced in §18 Open Questions.

### 4.5 → L5 (policy engine)

```
CompiledPolicyDefaults {
  preset_recommendation: PresetId                  // L5 §6.4 mapping
  approval_mode_overrides: HashMap<Capability, ApprovalMode>
  privacy_posture: PrivacyPosture                  // mirrors CompiledRouting.privacy_posture
  privileged_profile: bool                         // per L5 §13.1039 Q10 resolution: persona property
  // NOTE (I-1): these are DEFAULTS. L5 composes under §6.3 precedence.
  // Persona cannot widen past hardcoded blocks, cannot widen past user-override,
  // cannot cause Low/Medium auto for High/Critical capabilities.
}
```

L5 reads this at `persona_swap_commit` (L5 §6.1 — `PersonaOverlayRef` in `CompiledMatrix`) and recompiles its matrix. Session-duration grants belonging to the outgoing persona are revoked before first post-swap evaluate (L5 §7, cascading persona-swap).

### 4.6 → L7 (trust UX / onboarding)

```
PersonaSummary {
  persona_id: PersonaId
  display_name: String
  tagline: String
  description: String
  archetype: Archetype                             // 17 §Archetype catalog (12)
  avatar_preview_ref: AssetRef                     // portrait.png
  sample_wav_ref: AssetRef                         // voice/sample.wav
  default_preset_recommendation: PresetId          // L7 §4.338 "Recommended for you" badge
  provenance_status: Trusted | Unverified | PrivilegedOverlay
  license_summary_ref: AssetRef                    // metadata.yaml
  version: SemVer
  privileged_profile: bool                         // L7 hides persona entirely unless Don's profile
}
```

### 4.7 Unified emission

All five consumer sub-structs and the summary are bundled into a single event:

```
compiled_persona_ready {
  persona_id: PersonaId
  version: SemVer
  change_id: ChangeId
  compiled_at: MonotonicTimestamp
  artifact_ref: CompiledPersonaHandle              // X3 §2.2 typing
  provenance_status: enum
}
```

Every subscriber reads the handle and pulls its sub-struct. No consumer re-parses YAML (L6 plan §Why must-own).

---

## 5. Compilation process

### 5.1 Stages (deterministic pipeline)

```
[1] pack load          — adapter reads persona.yaml, voice.yaml, metadata.yaml as typed structs
[2] schema validation  — every rule in §3 + 17 §Validation rules
[3] version migration  — schema_version < current → run typed up-migrations
[4] defaults fill      — unspecified v2 fields filled from SystemPersonaDefaults
[5] onboarding merge   — L7 wizard answers applied (persona selection, style overrides)
[6] user overrides     — confirmed overrides from user profile store applied
[7] observed-style     — confirmed-only entries applied from §13 journal
[8] conflict resolve   — precedence rule: user-override > onboarding > observed-style > persona-default > system-default
                         (this is the persona-side precedence; distinct from L5's decision precedence in §6.3)
[9] privileged overlay — if persona.privileged_profile=true AND overlay signature valid AND build-time flag set:
                         merge overlay; else: strip privileged_profile + reject overlay-only fields
[10] artifact generate — typed Compiled* sub-structs produced (§4)
[11] signature verify  — ed25519 over (pack bytes || metadata.yaml bytes); sets provenance_status
[12] policy hand-off   — CompiledPolicyDefaults staged for L5 (L5 recompiles matrix on commit)
[13] commit + emit     — compiled_persona_ready fired on event bus with change_id
```

### 5.2 Determinism

- Pure function of `(pack bytes, user profile snapshot, onboarding snapshot, observed-style journal snapshot, overlay bytes or None, system defaults version)`.
- Same inputs → byte-identical `CompiledPersona` (L6 plan §Acceptance criteria, golden-file stability).
- Replay test: every compile is reproducible from the audit trail (replay corollary to L5 §9).
- Iteration order in rule sets is stable (sorted by stable key — capability enum ordinal, rule index).

### 5.3 Signing and trust levels

| Signature state | `provenance_status` | Allowed scopes |
|---|---|---|
| Signed, pinned key, first-party | `Trusted` | All non-privileged features; may set `policy_defaults` within non-privileged bounds |
| Signed, pinned key, privileged (Don's key) | `PrivilegedOverlay` | Privileged overlay (§7) |
| Unsigned or signature invalid | `Unverified` | Loads with warning; surfaced to trust center; `system_prompt` tagged *untrusted-context* propagated to L4 (`L4 §10`, `L6_plan §Risk 6`); CANNOT set `privileged_profile`; CANNOT write approval_mode_overrides that widen past preset (clamped to `ask` on any would-widen override) |

Contradiction check: L6 plan §Key risks #6 says unverified packs are flagged; §7 says they get clamped defaults. Both are compatible; stated together here so there is no silent loosening.

---

## 6. Governance — what users CAN and CANNOT configure

### 6.1 User CAN configure (via L7 settings, audit-logged)

- `relationship_mode`, `warmth`, `formality`, `initiative`, `expressiveness`, `memory_style`
- `visual.gaze_style`, `visual.intensity_bounds` within persona-declared ranges
- Non-privileged `autonomy_posture` recommendation (recommendation only — L5 preset remains authoritative)
- `phrase_pool_ref` selection (choose an alternate bundled pool)
- `routing_prefs.cost_preference`, `routing_prefs.tier_preference` (clamped by core.health)
- `policy_defaults.approval_mode_overrides` — but **only as user-overrides**, which in L5 §6.3 sit above persona-default. Setting them through the persona-authoring channel requires pack re-signing; setting them at runtime sets a *user override* (L5 records `issued_by = UserOverride`).

### 6.2 User CANNOT configure

- Override any `block.*` hardcoded rule (L5 §2.3). No UI path writes these.
- Escalate past the active preset's ceiling without L5 re-auth (L5 §5, `policy.set_preset` re-auth gate).
- Inject a custom `system_prompt` at runtime that bypasses compiled safeguards. User-custom system prompts can be added to a persona pack only through the authoring channel and re-loaded through the signing path (§5.3).
- Claim `privileged_profile: true` without the overlay signature and the build-time profile flag (§7).
- Mix the acknowledgment pool and the safety-deflection pool (I-5). UI cannot expose such a merge.

### 6.3 Precedence reinforcement (canonical from L5 §6.3)

For a given `(capability, persona, user)` decision in L5:

1. **Hardcoded blocks** — win. Persona cannot override.
2. **User override** — user-set rule compiled into the user-overrides layer.
3. **Persona default** — from `CompiledPolicyDefaults.approval_mode_overrides`.
4. **Preset default** — L5 preset rule.
5. **System default** — last-resort shipped rule.

Reinforced here so L6 authors never assume persona-default can flip a hardcoded deny to allow. It cannot.

---

## 7. Privileged-profile (Isabelle) overlay

### 7.1 Problem statement

Isabelle is "a privileged profile layer, not a fully separate base code stack" (`MASTER_OUTLINE_TREE §1.3`). Her persona pack is private, must widen some capability defaults (Don's known-good tools), add custom phrase pools, enable Isabelle-specific memory salience, and bind the Isabelle avatar pack — without any of that ever leaking to public distributables or bypassing L5 hardcoded blocks.

### 7.2 Mechanism

- **Private overlay path.** Resolver looks in a Don-configured path, default:
  - file:///C:/Users/dbhav/.aether/overlays/isabelle/
  - Path is never referenced from a checked-in public file. A build-time env (`AETHER_PRIVILEGED_OVERLAY_PATH`) points to it on Don's dev machine only.
- **Signing.** Overlay is signed by Don's local Ed25519 key. Build-time pinning embeds the public key only on Don's build profile (`--profile=isabelle`). Default public profile omits the key → overlay refuses to verify → refuses to load with privileged scope.
- **Build-time profile flag.** `cargo` feature `privileged-overlay` is off by default. Public and Pro builds cannot enable it. Only `--profile=isabelle` turns it on.
- **Runtime resolution.** On compile, if `persona.privileged_profile = true` in a pack:
  - If `privileged-overlay` feature OFF → strip the flag, refuse overlay-only fields, log warning. Load continues as non-privileged persona.
  - If feature ON AND signature valid → merge overlay fields per §5.1 stage 9.
  - If feature ON AND signature invalid → refuse compile, fall to MinimumTrust (§11).

### 7.3 What the overlay CAN do

- Widen `approval_mode_overrides` within preset + hardcoded-block ceilings. L5 still composes per §6.3; the overlay is still subject to hardcoded blocks (I-2).
- Provide private phrase pools (Isabelle-specific language).
- Enable Isabelle-specific memory salience rules (e.g. weight personal-project domain higher).
- Bind Isabelle avatar pack (which lives only in the overlay tree).
- Set `privileged_profile: true`, which L5 mirrors onto every audit record (`actor_persona.privileged_profile = true`, per L5 §13.1039 Q10 resolution).

### 7.4 What the overlay CANNOT do

- Bypass any hardcoded block (I-2).
- Bypass privacy-posture gate (L5 §10). Strict-posture + private-provenance payload still cannot route remote.
- Grant itself new capabilities without L5-issued grants. The overlay proposes defaults; L5 grants; every grant is audited.
- Ship in public distributables. Prevented by:
  - Build-time lint (per monorepo §4.1.4): compiler refuses to build non-`isabelle` profile if any `personas/` or `overlays/` path-matches Isabelle asset names.
  - Manifest diff at release: OSS Preview and Pro public manifests are compared against a deny-list pattern; presence of any Isabelle asset fails CI.
  - Signed-pack key is NOT shipped in public builds, so even if an asset leaked, it could not be verified as privileged.

### 7.5 Audit surface

Every privileged-overlay compile emits:
- `compiled_persona_ready { provenance_status: PrivilegedOverlay, persona_id, version, change_id }`
- An L5 audit record via `L5 §8` with `actor_persona.privileged_profile = true` on every subsequent `action_request` under that persona.

---

## 8. Hot-reload semantics

### 8.1 State machine

```
IDLE ──persona.compile(id)──▶ COMPILING
                                │
                                ├─ error ─▶ COMPILE_FAILED ──▶ (MinimumTrust fallback, §11)
                                │
                                └─ ok ────▶ STAGED
                                             │
                               ───persona.hot_reload(handle)───
                                             │
                                             ▼
                                        SWAP_BEGIN  (emits persona_swap_begin)
                                             │
                                 waits for L1 safe boundary (§8.2)
                                             │
                                             ▼
                                        SWAP_COMMIT (emits persona_swap_commit +
                                                     compiled_persona_ready)
                                             │
                                             ▼
                                           ACTIVE

Any stage timeout or consumer NACK (500 ms per L6_plan Risk 2) → SWAP_ROLLBACK → ACTIVE (old persona retained)
```

### 8.2 Safe boundary (coordinated with L1 §7.5)

L1 defines safe boundary as: (a) entry to `Idle`, (b) end of current `Speaking`, or (c) end of current `AcknowledgingWait`. **Never mid-word, never mid-classification.** L6 waits for L1 to ack safe-boundary before emitting `persona_swap_commit`.

Strictness of boundary is **L1/L6 open question 7** (from L1 plan line 1012). This document defers to L1 for the final strictness choice; the compiler supports both modes via a config knob (`hot_reload.boundary_strictness = Strict | Relaxed`).

### 8.3 During swap

- L1 buffers no new ack phrases until commit (L1 §7.5 hot-swap). In-flight turn uses old persona to completion.
- L3 interpolates visual params across a blend window (`visual_blend_window_ms`, default 400 ms) to avoid snap changes. Clamped by `anti_uncanny_settings`.
- L4 lets any in-flight route finish with the old persona (`L4 §766 persona_swap_commit`). Next route uses new persona.
- L5 revokes session-duration grants issued under outgoing persona and recompiles the matrix with the new `PersonaOverlayRef` (L5 §7 cascading persona swap, §6.1).
- L2 leaves existing memories untouched; salience rule set flips atomically; new queries use new rules.
- L7 shows the swap banner (L7 §8.540).

### 8.4 Failure during swap

- Any consumer NACK or timeout → `persona_swap_rollback` event; old persona remains active; compiler stays in `STAGED`.
- User surfaced via L7 error banner.
- Audited via L5 with `reason = persona_swap_failed`.
- Does not leave system in partial state: atomicity enforced by the begin/commit split (L6_plan Risk 2).

---

## 9. Interfaces (typed pseudotype)

### 9.1 Emitted events (via Rust event bus, projected to UI per X3 §5)

| Event | Payload (abbrev.) | Emitted by | Consumed by |
|---|---|---|---|
| `persona_swap_begin` | `persona_id, previous_id, change_id, compile_time_ms` | L6 | L1, L2, L3, L4, L5, L7 |
| `persona_swap_commit` | `persona_id, change_id` | L6 | L1, L2, L3, L4, L5, L7 |
| `persona_swap_rollback` | `persona_id, reason, change_id` | L6 | L1, L2, L3, L4, L5, L7 |
| `compiled_persona_ready` | `persona_id, version, change_id, compiled_at, artifact_ref, provenance_status` | L6 | L1, L2, L3, L4, L5, L7 |
| `persona_compile_failed` | `persona_id, version, reason, change_id` | L6 | L7, L5 (audit) |
| `persona_observed_style_proposed` | `persona_id, field_path, proposed_value, evidence_ref` | L6 | L7 (confirmation UI), L5 (audit) |

### 9.2 Subscribed events

| Event | Source | Compiler reaction |
|---|---|---|
| `policy_decision` | L5 | record persona-scoped enforcement feedback for diagnostics (no auto-adjust) |
| `onboarding.step_saved` | L7 | stage onboarding inputs for next compile |
| `persona.user_override_set` | L7 | stage user override; mark compile dirty |
| `persona.observed_style_confirmed` | L7 | append to confirmed-overrides journal; mark compile dirty |
| `core.health.tier_changed` | Core | re-emit CompiledRouting if tier-clamped values change |

### 9.3 Rust trait (pseudotype)

```
trait PersonaCompiler {
  fn list(&self) -> Vec<PersonaSummary>;
  fn get(&self, id: PersonaId) -> Result<PersonaSummary, PersonaError>;
  fn compile(&self, id: PersonaId) -> Result<CompiledPersonaHandle, PersonaError>;
  fn hot_reload(&self, handle: CompiledPersonaHandle) -> Result<ChangeId, PersonaError>;
  fn validate(&self, pack: PersonaPackRef) -> ValidationReport;
  fn subscribe(&self, filter: PersonaEventFilter) -> EventStream<PersonaEvent>;
  fn set_user_overrides(&self, id: PersonaId, ov: UserOverrides) -> Result<ChangeId, PersonaError>;
  fn export(&self, id: PersonaId) -> Result<Uri, PersonaError>;     // L5-gated
}
```

---

## 10. Tauri IPC commands (align with X3 §2.2)

Commands listed in `X3 §2.2 persona.*` are the base three. This design extends with authoring and override surfaces needed by L7.

| Command | Request | Response | Errors | Side effects | Blocking? | L5-gated? |
|---|---|---|---|---|---|---|
| `persona.list` | `()` | `Vec<PersonaSummary>` | `Degraded` | none | non-blocking | no |
| `persona.get` | `{ id }` | `PersonaSummary` | `NotFound`, `Degraded` | none | non-blocking | no |
| `persona.compile` | `{ id }` | `CompiledPersonaHandle` | `ValidationFailed`, `SignatureInvalid`, `VersionMismatch` | stages new CompiledPersona | may be long (large pools) | no |
| `persona.hot_reload` | `{ handle }` | `ChangeId` | `SwapRolledBack`, `BoundaryTimeout` | persona_swap_* events; L5 grant revoke | blocking until commit/rollback | no (but L5 audits) |
| `persona.validate` | `{ pack: PersonaPackRef }` | `ValidationReport` | `PackNotFound` | none (authoring helper) | non-blocking | no |
| `persona.authoring.preview` | `{ pack, test_inputs }` | `PreviewBundle` | `ValidationFailed` | ephemeral compile, not committed | non-blocking | no |
| `persona.set_user_overrides` | `{ id, overrides }` | `ChangeId` | `OverrideDenied`, `Clamped` | writes to user profile store; triggers recompile | may trigger re-auth | **yes** when overrides touch approval_mode_overrides |
| `persona.export` | `{ id }` | `Uri` | `Denied`, `NotFound` | writes archive to approved path | blocking | **yes** (L5 ResourceScope + re-auth per L5 §5.515) |
| `persona.observed_style.confirm` | `{ proposal_id }` | `ChangeId` | `NotFound`, `Expired` | journal append; recompile | non-blocking | audited by L5 |
| `persona.observed_style.reject` | `{ proposal_id }` | `()` | `NotFound` | journal append (rejected) | non-blocking | audited by L5 |

Authoring commands (`validate`, `authoring.preview`) are legitimately TS-side tooling helpers per `X3 §171`: "Compiler in Rust … authoring/validation helpers may live in TS for onboarding." The *compile path itself* remains Rust-only.

---

## 11. Failure and degraded modes

Every failure class has (a) detection, (b) effect, (c) user surface, (d) recovery.

| # | Class | Detection | Effect | User surface | Recovery |
|---|---|---|---|---|---|
| 11.1 | **Invalid persona config** (required fields missing, enum invalid, size bounds violated) | Stage 2 schema validation | Refuse compile; no staged artifact | L7 banner "Persona '<id>' failed validation — see detail"; list of violations | Author fixes pack; re-invoke `persona.compile` |
| 11.2 | **Partially missing values** (optional fields absent) | Stage 4 defaults fill | Fill from `SystemPersonaDefaults`; warn | Trust center warning list | User may add overrides; persona continues |
| 11.3 | **Version mismatch** (pack newer than compiler) | Stage 1 load | Refuse load | L7 banner "Pack requires newer Aether version"; upgrade CTA | Update product |
| 11.4 | **Schema migration failure** (v1→v2 migration throws) | Stage 3 migration | Refuse load; log migration error | L7 banner "Pack migration failed"; author contact line | File issue; fix migration |
| 11.5 | **Signature verification fail on privileged overlay** | Stage 11 signature verify, privileged path | Refuse as privileged; strip `privileged_profile`; fall through to non-privileged load or refuse entirely (configurable) | Trust center "Privileged overlay signature invalid — running as non-privileged" | Re-sign or rotate key |
| 11.6 | **Signature fail on non-privileged pack** | Stage 11 signature verify | Load as `Unverified`; clamp approval_mode_overrides to `ask` on any would-widen override; tag `system_prompt` untrusted-context (L4) | Trust center "Pack unverified — behavior sandboxed" | User can accept unverified; or remove pack |
| 11.7 | **Runtime compile exception** (panic, OOM, I/O error) | Stage catch-all | Revert to previously active CompiledPersona if any; else MinimumTrust | L7 banner; L5 audit | Next `persona.compile` retry |
| 11.8 | **Persona file corruption** (YAML parse fail, binary asset CRC mismatch if present) | Stage 1–2 | Quarantine pack (move to `personas/_quarantine/<id>/`); refuse load | Trust center "Pack quarantined — file corruption"; diagnostic link | Author or user restores clean pack |
| 11.9 | **Hot-reload timeout / consumer NACK** | Stage SWAP_BEGIN, 500 ms window | Roll back; emit `persona_swap_rollback`; old persona remains | L7 "Persona swap failed — reverted" | User retries or picks different persona |
| 11.10 | **No persona loads at startup** (all fail) | After initial compile sweep | Activate `MinimumTrust` per L5 §11.4 | L7 "Minimum-trust mode" banner | Once any persona compiles, swap to it |

**MinimumTrust persona** is the baked-in `SystemPersonaDefaults` shipped in the Rust binary. It is not a file; it is a compile-time constant. Its `CompiledPolicyDefaults` maps every capability to `deny` except the tiny read-only set L5 §11.4 enumerates. Its `CompiledLanguage` includes only the hardcoded-allowed deflection pool (L1 §10.5).

---

## 12. Versioning and migration

### 12.1 Versioning

- `persona.yaml.schema_version: u32` — bumps on any *breaking* field semantics change.
- `persona.version: semver` — bumps on persona *content* change (new phrase pool, tweaked system prompt). Does not invoke migration.
- Compiler exposes `compiler_schema_version: u32` in its own build metadata.

### 12.2 Migration rules

- **Up-migration only.** Never remove fields (`17 §Future-proofing`).
- Each schema version bump ships with a typed up-migration function in `compiler::migrate::v{N-1}_to_v{N}`.
- Migration is deterministic and fully testable; every historical version retained as a test fixture (L6_plan acceptance: schema migration correctness).

### 12.3 Backward / forward compat

- **Older pack, newer compiler:** migrate up; succeed.
- **Newer pack, older compiler:** refuse load with `VersionMismatch`. Surface upgrade CTA (§11.3).
- **Compiler cannot silently drop unknown fields.** Unknown fields are preserved in a `_unknown: HashMap<String, Value>` bag on the parsed pack struct and warned (§3 validation obligations).

### 12.4 Migration audit

Every up-migration emits a one-time audit record (via L5 §8) `persona_schema_migrated { persona_id, from_version, to_version, change_id }`. Enables auditability for "why did this persona's behavior change after an update?"

---

## 13. Observed-style input — carefully bounded

### 13.1 Principle

**No silent learning** (I-8). The compiler never rewrites persona fields from observed interactions. Ever.

### 13.2 Flow

1. **Signal collection.** A bounded set of signal emitters (not the full turn log) may propose style updates: e.g., "user corrected persona to be more concise 3 times this session." Emitters are shipped with the build; community packs cannot add new emitters.
2. **Proposal.** L6 emits `persona_observed_style_proposed { persona_id, field_path, proposed_value, evidence_ref }`.
3. **Confirmation UI.** L7 surfaces the proposal in settings with "Apply once / Apply always / Dismiss."
4. **Confirmation event.** `persona.observed_style.confirm { proposal_id }` → L6 appends to confirmed-overrides journal → marks compile dirty → recompiles on next safe boundary.
5. **Audit.** Every proposed/confirmed/rejected transition lives in the L5 audit log.

### 13.3 Decay

- **Unconfirmed proposals decay** after a bounded window (default 7 days; configurable per proposal kind). Decayed proposals are removed from the pending queue and journaled as `expired`.
- **Confirmed updates persist** in the confirmed-overrides journal until explicitly reverted by the user in settings.

### 13.4 What observed-style CAN change

- `identity.warmth`, `formality`, `initiative`, `expressiveness` (within bounds).
- Phrase-pool selection (pick an alternate bundled pool).
- `language.preferred_phrasing_axes` numerics.

### 13.5 What observed-style CANNOT change

- Anything in `policy_defaults` (I-1).
- `privileged_profile`.
- `privacy_posture`, `cost_preference`, provider pins.
- `boundaries` list (safety-adjacent).
- `system_prompt` content.

---

## 14. Stub interfaces (unblock L1/L2/L3/L4/L5/L7)

So every consumer can code against L6 before L6 ships:

### 14.1 Stubs provided

- **Rust** crate `l6-persona-stub` implementing `PersonaCompiler` trait with:
  - one fixture persona (`aurora_default`) — returns a hand-authored `CompiledPersona` matching the §4 shapes.
  - scripted hot-reload: tests can invoke `hot_reload(fixture_v2)` to drive `persona_swap_begin` / `persona_swap_commit` sequences.
  - scripted failure modes (`inject_compile_fail`, `inject_boundary_timeout`).
- **TS** bindings auto-generated (via `ts-rs` per L6_plan §Borrowable-vs-custom) mirroring the Rust structs. L7 uses these directly.
- **Event fixtures** published as JSON golden files for each event in §9.1, consumed by L1/L4/L5/L7 tests.

### 14.2 What each consumer gets from the stub

- **L1** (per L1 §7.5, §14.916): `CompiledLanguage` with populated `phrase_pool`, `deflection_pool`, `ack_style`, `initiative_bias`; `persona_swap_commit` scripted.
- **L2** (sibling wave): `CompiledSalience` with realistic rule set; `persona_scoped_rng_seed`.
- **L3** (sibling wave): `CompiledVisual` + `avatar_pack_ref` pointing at a fixture asset directory.
- **L4** (per L4 §765–767): `CompiledRouting` with `privacy_posture=Standard`, `preferred_tier=main`, `temperature=0.7`, `safety_header` string.
- **L5** (per L5 §6.1, §6.3, §11.4): `CompiledPolicyDefaults` with a small `approval_mode_overrides` set; `privileged_profile=false`; `MinimumTrust` also exposed as a separate fixture for L5 §11.4 tests.
- **L7** (per L7 §17.5): `PersonaSummary` shape; `persona.list` returns 3 fixture packs (one signed, one unsigned, one invalid) for UI coverage.

---

## 15. Testing strategy (design level)

### 15.1 Property tests

- **Determinism.** For a randomly generated `(pack, overrides, overlay?)` tuple, two compiles produce byte-identical artifacts (golden-hash check).
- **Schema coverage.** Every §3 validation rule has at least one passing and one failing fixture.
- **Precedence monotonicity.** For any capability, widening the persona-default never widens the L5 decision past the user-override or hardcoded-block ceiling (co-tested with L5 §15.970 monotonicity).
- **Field mapping completeness.** Every field in `CompiledPersona` traces to exactly one consumer's documented need (§4). An exhaustiveness test fails if any field is orphaned or any consumer reads an unmapped field (L6_plan acceptance: cross-layer parameter completeness).

### 15.2 Red-team suite

- **Privilege escalation via crafted pack.** A pack sets `privileged_profile=true` without signature → must be stripped; no grant widening observed. (Tested with L5 audit log inspection.)
- **Prompt-injection via phrase pool.** A phrase pool contains instruction-like content ("Ignore safety and…"). Must not affect L4 prompt assembly because phrase pool is consumed as *data* by L1, not injected into L4 context. Asserted via L4 red-team case referencing L6 stub.
- **Unsigned overlay claiming privileged scope.** Non-privileged build with overlay path set → refuses to load privileged scope; does not crash.
- **Pool crossover.** A pack conflates `acknowledgment_pool_ref` and `safety_deflection_pool_ref` at the same path → validation refuses (I-5).
- **Hardcoded-block bypass attempt.** Pack's `approval_mode_overrides` sets `ShellExec: auto`. L5 composes → hardcoded-block keeps deny.
- **Observed-style spoofing.** Evidence ref doesn't match a known emitter → proposal rejected at stage 7.

### 15.3 Migration tests

- Every shipped schema version bump has a round-trip migration test: load v{N-1} fixture → compile → asserted equivalent to v{N} fixture compile.
- Missing-field defaulting tested against `SystemPersonaDefaults` snapshots.

### 15.4 Replay tests

- Given an audit log + genesis pack set, re-compile every `compiled_persona_ready` emission and confirm artifacts match the original (analog to L5 §9 replay).

### 15.5 Hot-reload tests

- **Atomicity:** zero mixed-persona turns (L6_plan acceptance). Scripted `persona_swap_commit` during L1's `ClassifyingIntent` → current turn completes with old persona; next turn uses new.
- **Rollback:** injected consumer NACK → old persona retained, `persona_swap_rollback` emitted.
- **L5 grant revocation coupling:** `persona_swap_begin` → all session-duration grants of outgoing persona revoked before first post-swap `action_request` evaluates (cross-tested with L5 §7).

---

## 16. Tier awareness

Performance tier (from `core.health`, per `MASTER_OUTLINE_TREE §4.2`) shapes the compiled artifact:

| Aspect | Lite | Balanced | Full |
|---|---|---|---|
| `CompiledLanguage.phrase_pool` size | ~1/3 variants (L1 §8.3) | full | full |
| `CompiledLanguage.deflection_pool` size | full (never trimmed — safety) | full | full |
| `CompiledVisual.visual_params.target_fps` | clamped to Lite tier max | tier max | pack default |
| `CompiledSalience.salience_rules` | coarser (groups adjacent rules into ranges) | full | full |
| `CompiledRouting.provider_pins` | **ignored** (P2+ feature; Lite uses defaults) | honored if granted | honored if granted |
| `CompiledRouting.remote_bias` | downweighted (prefer local) | neutral | per persona |
| Observed-style proposal cadence | reduced (fewer emitters) | normal | normal |

Tier is read at compile time; tier change emits `core.health.tier_changed` → L6 recompiles if any tier-clamped field would materially change (L1 §11.795 analog).

---

## 17. Deliverables summary (build order for implementer)

In priority order — the minimum set that unblocks L1/L2/L3/L4/L5/L7 stubs:

1. **Persona pack schema + YAML loader (Rust).** Implements §3, `17_*`, via `serde_yaml` behind a typed adapter.
2. **Validation + migration pipeline.** Stages 2–3 of §5.1; v1→v2 migration + fixture-based tests.
3. **Compiler core.** Stages 4–10; emits typed `CompiledPersona` with all §4 sub-structs.
4. **Signature verifier.** Ed25519 + pinned key; staged as §5.3; drives `provenance_status`.
5. **Hot-reload state machine.** §8; two-phase swap with L1 safe-boundary coordination; `persona_swap_*` events.
6. **IPC commands.** `persona.list`, `persona.get`, `persona.compile`, `persona.hot_reload` as MVP (per X3 §2.2); the rest follow.
7. **Privileged-overlay resolver.** §7; gated by build-time `privileged-overlay` feature + `--profile=isabelle`; never shipped in public builds.
8. **Observed-style pipeline.** §13; proposal emission + confirmed-overrides journal + L7 hook.
9. **Stubs + TS bindings.** §14; unblocks all other layers immediately.
10. **Golden-file + red-team test suite.** §15; CI gates.

---

## 18. Open questions

1. **Safe-boundary strictness (strict vs relaxed).** Inherited from L1 §1012 Q7. Compiler supports both; needs Don to lock.
2. **TS-binding generator.** `ts-rs` vs `specta` vs hand-written (L6_plan §Open decisions). Recommend `ts-rs`.
3. **First-party signing scheme.** Ed25519 + pinned key in build vs OS-keychain-managed. Recommend Ed25519 + pinned.
4. **P0 hot-reload vs single-persona-at-startup.** Tradeoff: OSS Preview scope (L6_plan §Open decisions).
5. **Terminology reconciliation: `tier_preference` overload.** `17_*` uses it for model tier (`fast|main|heavy`); `L4 §87` uses it for perf tier (`Lite|Balanced|Full`). Document uses both explicitly. Recommend renaming persona field to `model_tier_preference` in schema v2 to avoid overload — flagged but not done (no cross-doc edits).
6. **Persona-scoped RNG seeding vs L2 reproducibility.** L6_plan §Open decisions. Needs L2 contract.
7. **Exactly which sub-structs L7 consumes vs. reads directly from `metadata.yaml`.** L6_plan §Open decisions.
8. **Observed-style emitter set.** Exact emitter list deferred to P2+; §13 only specifies the *channel*, not the specific signals.
9. **Overlay path configuration.** Is `AETHER_PRIVILEGED_OVERLAY_PATH` the final mechanism, or should it be a signed manifest entry? Current choice: env var; revisit at X3 signed-updater design.
10. **Pack-marketplace trust model (P4).** When community packs appear, do we require signing by the marketplace, or only by authors? Deferred until P4.
11. **Archetype enum surface to L4.** Does L4 want `archetype` as a routing signal, or is `privacy_posture + cost_preference + preferred_tier` enough? Current choice: not surfaced to L4; flagged.

---

## 19. Contradictions discovered (flagged, not silently resolved)

- **§4.4 tier terminology overload.** `17_*` and `L4 §87` use the same name (`tier_preference`) for different concepts. Recorded in §4.4 and §18 Q5. Neither redefined; compiler emits both under distinct names (`tier_preference` for perf tier, `llm_preferences.preferred_tier` for model tier) to keep both upstream docs valid.
- **§5.3 vs §11.6 on unverified packs.** L6_plan §Risk 6 says "flagged `unverified`"; L6_plan §Acceptance says "treated as untrusted-context for L4." Compatible, but compounded treatment (flag + clamp + untrusted-tag) is stated here explicitly to avoid partial implementation.
- **§7 overlay path non-doctrine.** No canonical doctrine file specifies the overlay path; this doc proposes `file:///C:/Users/dbhav/.aether/overlays/isabelle/` as a default. Flagged in §18 Q9.
- **`L5 §13.1039 Q10` resolved privileged_profile as a persona property.** This doc adopts that resolution; if L5 plan is ever updated to move it, L6 must update accordingly.
- **Observed-style has no schema entry in `17_*`.** Not a contradiction — observed-style lives in a separate journal, not in the pack — but recorded in §2 because it's easy to mistake as a missing pack field.

---

## 20. Self-review checklist

- [x] Every runtime-affecting field validated (§3 validation obligations).
- [x] Every `Compiled*` artifact maps to a consumer layer (§4 — L1/L2/L3/L4/L5/L7; §15.1 exhaustiveness test enforces).
- [x] Precedence rule reinforces L5 decision authority (I-1, §6.3).
- [x] §7 Isabelle overlay is L5-compliant; cannot bypass hardcoded blocks or privacy posture (I-2, §7.4).
- [x] §11 has a degraded-mode entry per failure class (10 rows covering invalid, missing, version, migration, signature privileged, signature non-privileged, runtime exception, corruption, hot-reload timeout, no-persona-loads).
- [x] §14 gives every consumer enough stub surface (L1/L2/L3/L4/L5/L7 each itemized).
- [x] Contradictions flagged not silently resolved (§19).
- [x] Deterministic, replayable, auditable (I-3, §5.2, §15.4).
- [x] No silent learning (I-8, §13).

---

## 21. Cross-references

- file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether-planning/MASTER_OUTLINE_TREE.md
- file:///C:/Users/dbhav/Projects/aether-planning/17_persona_pack_schema.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_engine.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md
