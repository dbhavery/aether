// Types mirroring the Rust command payloads. Hand-maintained for v0;
// a `ts-rs` codegen pass can replace this once the command surface
// stabilises (see ARCHITECTURE.md).

export interface CompanionBanner {
  persona_id: string;
  persona_name: string;
  persona_version: string;
  preferred_tier: string;
  provider_mode: "reflex_stub" | "ollama";
  provider_label: string;
  output_detail: "terse" | "balanced" | "verbose";
  tagline: string;
  system_prompt: string;
}

export interface MessageMeta {
  tier: string | null;
  provider: string | null;
  /** Vision- or speech-route model id, when the assistant message
   * came from a provider that exposes one. Mirrors
   * `TelemetryEntry.model` so transcript bubbles, the per-panel
   * hint, and the Trust drawer all show the same identifier for
   * the same turn. Absent for text-only turns and for adapters that
   * don't report a model. */
  model?: string;
  // Optional because the Rust side `#[serde(skip_serializing_if = "Option::is_none")]`
  // drops these fields when absent; treat missing as "not reported".
  latency_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  /** Modality origin tag. `"voice"` when the turn was driven by a
   * push-to-talk transcribe_utterance call, `"vision"` when driven
   * by a camera/screen analyze_frame call. Text-only turns omit
   * this field. Voice V1 step 5 introduced the field. */
  origin?: "voice" | "vision";
}

export interface TranscriptMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sequence: number;
  timestamp_ms: number;
  meta: MessageMeta | null;
  /**
   * Wave 16 — frontend-only variant tag set by the chat surface when
   * appending an outcome whose `TurnOutcomeKind === "draft_only"`. The
   * Rust side does not populate this field; it is purely a renderer
   * cue so Transcript.tsx can show a distinct "DRAFT ONLY" affordance
   * instead of the generic system-message styling.
   */
  variant?: "draft_only";
}

export interface ApprovalPayload {
  ticket_id: string;
  capability: string;
  scope: string;
  reason: string;
  risk_hint: string;
  /**
   * Wave 15 — whether the request belongs to a task lineage. Gates the
   * `allow_task` radio option in the modal (T1.3 §5.1). When false the
   * modal hides the option because selecting it would be a no-op.
   */
  task_id_present: boolean;
  /**
   * Wave 15 — whether the capability has side effects. Gates the
   * `defer_draft` radio option (T1.3 §5.1). Read-only capabilities
   * cannot meaningfully be "drafted".
   */
  side_effecting: boolean;
}

/**
 * Wave 14 (T1.3 §5.3) — TS mirror of the Rust `UserChoiceWire` tagged
 * enum. The five variants the L7 approval modal surfaces map 1:1 onto
 * L5's `UserChoice` (`Allow` / `AllowSession` / `AllowTask` /
 * `DeferToDraft` / `Deny`). Wire form is `{ kind: "<snake_case>" }`
 * matching `#[serde(tag = "kind", rename_all = "snake_case")]` on the
 * Rust side.
 *
 * Display order in the modal radio (per design §5.1):
 *   1. allow_once   → `Allow`
 *   2. allow_task   → `AllowTask`
 *   3. allow_session → `AllowSession`
 *   4. defer_draft  → `DeferToDraft`
 *
 * Plus a separate "Decline" button outside the radio group that emits
 * `Deny` — the safety-default escape, not a scope choice.
 */
export type UserChoice =
  | { kind: "allow" }
  | { kind: "allow_session" }
  | { kind: "allow_task" }
  | { kind: "defer_to_draft" }
  | { kind: "deny" };

/** Stable wire ids for the four radio options, in fixed display
 * order per design §5.1. The "deny" button is intentionally NOT in
 * this list — it lives outside the radio group. */
export const APPROVAL_RADIO_OPTIONS: ReadonlyArray<{
  id: "allow_once" | "allow_task" | "allow_session" | "defer_draft";
  label: string;
  /** The `UserChoice` value emitted when this radio option is
   * submitted via the Approve button. */
  choice: UserChoice;
}> = [
  { id: "allow_once", label: "Allow once", choice: { kind: "allow" } },
  {
    id: "allow_task",
    label: "Allow for this task",
    choice: { kind: "allow_task" },
  },
  {
    id: "allow_session",
    label: "Allow for this session",
    choice: { kind: "allow_session" },
  },
  {
    id: "defer_draft",
    label: "Draft only — let me run it",
    choice: { kind: "defer_to_draft" },
  },
];

export type TurnOutcomeKind =
  | "completed"
  | "awaiting_approval"
  | "denied"
  | "needs_upgrade"
  | "draft_only"
  | "provider_error";

export interface TurnOutcome {
  turn_id: string;
  kind: TurnOutcomeKind;
  message: TranscriptMessage | null;
  approval: ApprovalPayload | null;
  error_note: string | null;
}

/**
 * Wave 11 — `resolve_approval` Tauri command now returns a tagged
 * variant so the same wire surface serves both the chat-surface
 * (`PendingApproval::Turn`) and Wave 11 executor
 * (`PendingApproval::Executor`) flavours. The renderer dispatches on
 * `kind`:
 *
 * - `"turn"` carries the original `TurnOutcome` shape so the chat
 *   surface keeps working with zero TS-side branching.
 * - `"executor"` carries `{ approved, method, result, error }`. The
 *   renderer routes the reply by `method` to whichever surface
 *   originally issued the call.
 */
export type ResolveApprovalReply =
  | { kind: "turn"; outcome: TurnOutcome }
  | {
      kind: "executor";
      approved: boolean;
      method: string;
      result: string | null;
      error: string | null;
    };

/**
 * Wave 11 — payload carried on the `executor:awaiting_approval` Tauri
 * event. Same shape as `ApprovalPayload`; emitted by the gate's Ask
 * branch alongside the sentinel error string `awaiting_approval:<id>`
 * surfaced as the inner's `Result` so the renderer can show the modal
 * even if the event listener isn't attached.
 */
export type ExecutorAwaitingApproval = ApprovalPayload;

/** Wire prefix for the gate's "awaiting approval" sentinel error string. */
export const AWAITING_APPROVAL_SENTINEL_PREFIX = "awaiting_approval:";

export type PresenceStateLabel =
  | "quiet"
  | "listening"
  | "thinking"
  | "awaiting-approval"
  | "responding";

export interface PresencePayload {
  state: PresenceStateLabel;
  detail: string | null;
  updated_at_ms: number;
}

export type AuditDecisionLabel =
  | "allow"
  | "ask"
  | "deny"
  | "needs_upgrade"
  | "draft_only_system"
  | "draft_only_user_choice";

/** ADR-0009 §Decision 2: one ranked memory hit shown on the audit row. */
export interface TrustRetrievalHit {
  memory_id: string;
  domain: string;
  score: number;
}

/** ADR-0009 §Decision 2: retrieval-block summary shown on the audit row. */
export interface TrustRetrievalProvenance {
  block_present: boolean;
  hits: TrustRetrievalHit[];
}

export interface TrustAuditRow {
  audit_id: string;
  decision: AuditDecisionLabel;
  capability: string;
  scope: string;
  change_id: string;
  at_mono_ns: number;
  at_epoch_s: number;
  /**
   * ADR-0009 audit-row schema version. `1` for pre-2026-04-25 rows
   * (no user-phrasing fields populated); `2` for post-ADR-0009.
   * Backend stamps this on every projection; the renderer uses it
   * to choose between the legacy "schema badge + capability only"
   * view and the v2 "user-phrasing prominent, model-saw expandable"
   * view.
   */
  schema_version: number;
  /** ADR-0009 §Decision 1. v2 conversation rows only. */
  original_utterance?: string;
  /** ADR-0009 §Decision 2. v2 conversation rows where retrieval ran. */
  retrieval_provenance?: TrustRetrievalProvenance;
}

export interface PersonaCatalogEntry {
  id: string;
  name: string;
  tagline: string;
  stance: string;
  tone: string;
}

// --- Media permissions (P1) -----------------------------------------------

/** Tri-state per-device permission. Mirrors the Rust enum's wire format. */
export type MediaPermissionState = "allow" | "ask" | "deny";

/** Which device a permission targets. */
export type MediaKind = "camera" | "screen";

/**
 * Local-only permission posture for camera + screen capture. This is
 * the single point of truth the Settings UI renders and the future
 * capture/inference paths consult before touching the device.
 */
export interface MediaPermissions {
  camera: MediaPermissionState;
  screen: MediaPermissionState;
}

// --- Mic permission (Voice V1 step 1) -------------------------------------

/**
 * Local-only permission posture for the microphone. Separate from
 * `MediaPermissions` so the camera/screen consent and the mic consent
 * stay independently auditable. The tri-state vocabulary is shared
 * with `MediaPermissionState` — the mic does not invent new states.
 */
export interface MicPermission {
  state: MediaPermissionState;
}

// --- Single-frame analysis (P3) -------------------------------------------

/** Outcome kinds the `analyze_frame` command can return. */
export type FrameAnalysisKind =
  | "frame_analyzed"
  | "frame_blocked"
  | "permission_denied"
  | "permission_ask";

/** Result envelope from `analyze_frame`. Mirrors the Rust struct. */
export interface FrameAnalysisOutcome {
  turn_id: string;
  kind: FrameAnalysisKind;
  message: TranscriptMessage | null;
  error_note: string | null;
}

/** One registered vision provider entry. */
export interface VisionProviderInfo {
  id: string;
  label: string;
  active: boolean;
}

/** Status of the active vision provider (returned by `vision_status`). */
export interface VisionStatus {
  enabled: boolean;
  active_id: string | null;
  label: string | null;
  /** Active provider's current model id, if the adapter exposes one. */
  active_model: string | null;
  providers: VisionProviderInfo[];
}

/**
 * Result of `list_vision_models`. Errors are returned in-band as a
 * plain-language string so the UI can render a quiet "models
 * unavailable" hint without modal noise.
 */
export interface VisionModelList {
  provider_id: string | null;
  models: string[];
  error: string | null;
}

// --- Voice V1 step 5 -------------------------------------------------------

/** Outcome kinds the `transcribe_utterance` command can return. */
export type UtteranceKind =
  | "utterance_transcribed"
  | "utterance_blocked"
  | "mic_permission_denied"
  | "mic_permission_ask";

/** Result envelope from `transcribe_utterance`. Mirrors the Rust
 * struct. Errors surface as a thrown string (invalid utterance,
 * provider failure, no active speech provider). */
export interface UtteranceOutcome {
  turn_id: string;
  kind: UtteranceKind;
  message: TranscriptMessage | null;
  error_note: string | null;
}

/** Request payload for `transcribe_utterance`. */
export interface TranscribeUtteranceRequest {
  utterance_data_url: string;
  duration_ms: number;
  cue: string | null;
  sample_rate: number;
  channels: number;
  language: string | null;
}

/** One registered speech provider entry. */
export interface SpeechProviderInfo {
  id: string;
  label: string;
  active: boolean;
}

/** Status of the active speech provider (returned by `voice_status`). */
export interface VoiceStatus {
  enabled: boolean;
  active_id: string | null;
  label: string | null;
  active_model: string | null;
  providers: SpeechProviderInfo[];
}

/** Result of `list_speech_models` / `refresh_speech_models`. */
export interface SpeechModelList {
  provider_id: string | null;
  models: string[];
  error: string | null;
}

// --- Presence V1 step 1 ---------------------------------------------------

/** Snapshot of the local presence configuration. Observational
 * only — no L5 capability gate, no audit rows. Mirrors the Rust
 * `PresenceConfig` struct in apps/desktop/src-tauri/src/presence_config.rs.
 */
export interface PresenceConfig {
  enabled: boolean;
  idle_after_s: number;
  away_after_s: number;
  history_in_trust_drawer: boolean;
}

// --- Presence V1 step 2 ---------------------------------------------------

/** User-attention state from the OS-idle controller. */
export type UserAttentionLabel = "active" | "idle" | "away";

/** Status payload from `presence_status`. `state` is meaningless when
 * `enabled = false` — branch on the flag first. `probe_supported = false`
 * means the platform idle probe (macOS / Linux today) has not shipped
 * a real implementation yet; the UI should surface this truthfully. */
export interface PresenceStatusPayload {
  state: UserAttentionLabel;
  since_ms: number;
  idle_seconds: number;
  enabled: boolean;
  probe_supported: boolean;
  idle_after_s: number;
  away_after_s: number;
}

/** One row of presence history. `kind = "presence_state_changed"` is
 * the only value surfaced in step 2. */
export interface PresenceHistoryEntry {
  kind: "presence_state_changed";
  from: UserAttentionLabel;
  to: UserAttentionLabel;
  idle_seconds: number;
  at_ms: number;
}

/** Payload emitted on the `presence:attention` event bus on every
 * transition. Same shape as `PresenceHistoryEntry`. */
export type AttentionEventPayload = PresenceHistoryEntry;

/** Inclusive bounds enforced by `set_presence_config` on the Rust
 * side. The Settings UI mirrors these to reject bad input before the
 * round trip. */
export const PRESENCE_THRESHOLD_MIN_S = 10;
export const PRESENCE_THRESHOLD_MAX_S = 86_400;

// --- Memory V2 step 2 ----------------------------------------------------

/** Six memory domains per `docs/MEMORY-V2-ARCHITECTURE.md` §1. */
export type MemoryDomain =
  | "session"
  | "durable"
  | "facts"
  | "projects"
  | "preferences"
  | "artifacts";

export const MEMORY_DOMAINS: MemoryDomain[] = [
  "session",
  "durable",
  "facts",
  "projects",
  "preferences",
  "artifacts",
];

/** Per-domain write risk posture. Mirrors the tri-state the media /
 * mic permissions use. Design §4. */
export type MemoryRisk = "auto" | "ask" | "deny";

/** Shape of `memory.json` — matches the Rust `MemoryConfig` struct
 * in apps/desktop/src-tauri/src/memory_config.rs. All maps are
 * partial — missing entries fall back to design defaults on the
 * backend, so the UI can render a consistent row count either way.
 */
export interface MemoryConfig {
  /** Per-domain retention in days. `null` = keep forever. */
  retention_days: Partial<Record<MemoryDomain, number | null>>;
  /** Per-domain default risk posture for writes. */
  default_risk: Partial<Record<MemoryDomain, MemoryRisk>>;
  /** Embeddings opt-in block. Default: disabled, no provider. */
  embeddings: {
    enabled: boolean;
    provider: string | null;
  };
  /** Retrieval wiring config — ADR-0005. `max_items` gates the top-K
   * cap `submit_turn` passes to `run_retrieval_context`. Default 5;
   * `0` disables injection without flipping `embeddings.enabled`. */
  retrieval: {
    max_items: number;
  };
}

// --- Memory V2 step 4 — Trust drawer Memory tab --------------------------

/** Privacy class per `docs/MEMORY-V2-ARCHITECTURE.md` §1. Facts and
 * Artifacts are user-sensitive; the other four domains are standard.
 * Determined server-side and returned on the `MemoryListPayload`. */
export type MemoryPrivacyClass = "standard" | "user_sensitive";

/** One row in a Trust-drawer Memory lane. `memory_id` is the stable
 * "mem-{session_id}-{sequence}" handle used by the forget / edit
 * commands. */
export interface MemoryListItem {
  memory_id: string;
  sequence: number;
  timestamp_ms: number;
  role: string;
  content: string;
  source: string;
}

/** Per-domain response from `memory_list`. `items` is empty and
 * `empty_reason` is set for any domain whose backing store does not
 * yet exist (today: every domain except `session`). */
export interface MemoryListPayload {
  domain: MemoryDomain;
  privacy_class: MemoryPrivacyClass;
  risk: MemoryRisk;
  items: MemoryListItem[];
  empty_reason: string | null;
}

/** Discriminated union mirroring Rust `MemoryForgetOutcome`. The `kind`
 * tag is set by serde's `#[serde(tag = "kind", rename_all =
 * "snake_case")]`. */
export type MemoryForgetOutcome =
  | { kind: "allowed"; removed_count: number; audit_id: string }
  | { kind: "requires_approval" }
  | { kind: "denied"; reason: string }
  | { kind: "not_found" };

/** Discriminated union mirroring Rust `MemoryEditOutcome`. */
export type MemoryEditOutcome =
  | { kind: "allowed"; memory_id: string; audit_id: string }
  | { kind: "requires_approval" }
  | { kind: "denied"; reason: string }
  | { kind: "not_found" };

/** Design defaults mirrored client-side so the UI renders sensible
 * values before the first round trip completes, and so the Settings
 * "reset to defaults" button can work without a backend fetch. */
export const MEMORY_CONFIG_DEFAULTS: Readonly<MemoryConfig> = {
  retention_days: {
    session: null,
    durable: 30,
    facts: null,
    projects: null,
    preferences: null,
    artifacts: null,
  },
  default_risk: {
    session: "auto",
    durable: "auto",
    facts: "ask",
    projects: "auto",
    preferences: "auto",
    artifacts: "ask",
  },
  embeddings: {
    enabled: false,
    provider: null,
  },
  retrieval: {
    max_items: 5,
  },
};

// --- ADR-0006 hardware tier model ---------------------------------------

/** Three named tiers from ADR-0006 Decision 1. Wire form is the lowercase
 * variant name; matches Rust `tier::Tier`. */
export type Tier = "spark" | "flame" | "forge";

/** Coarse GPU classification from ADR-0006 §Decision 2. Mirrors Rust
 * `hardware::GpuKind`; wire form is snake_case. */
export type GpuKind =
  | "discrete_gpu"
  | "integrated_gpu"
  | "virtual_gpu"
  | "cpu"
  | "other";

/** Detected GPU info; matches Rust `hardware::GpuInfo`. All fields are
 * best-effort — vendors expose different detail through different
 * backends. `vram_gb_estimate` is a *lower bound* derived from
 * `wgpu::Limits::max_buffer_size`; may understate actual VRAM. */
export interface GpuInfo {
  vendor_id: string;
  device_name: string;
  kind: GpuKind;
  backend: string;
  vram_gb_estimate: number;
}

/** Hardware snapshot persisted into `tier.json`; matches Rust
 * `hardware::HardwareSnapshot`. `null`s indicate "not detected" /
 * "probe skipped" — the UI should render a clear neutral state, not
 * a zero. */
export interface HardwareSnapshot {
  gpu: GpuInfo | null;
  total_ram_gb: number;
  cpu_cores: number;
  disk_available_gb: number | null;
  ollama_gpu_loaded: boolean | null;
  detected_at_ms: number;
}

/** Persisted shape of `<app_data>/tier.json`. Matches Rust
 * `tier::TierConfig`. Settings UI reads `selected_tier` to decide
 * which tier card to highlight; reads `detected_tier` to badge the
 * recommendation; surfaces `manual_override` as the "your hardware
 * suggests X" hint when `selected !== detected`. */
export interface TierConfig {
  selected_tier: Tier;
  detected_tier: Tier;
  detected_at_ms: number;
  manual_override: boolean;
  hardware_snapshot: HardwareSnapshot;
}

// --- ADR-0007 retrieval readiness ---------------------------------------

/** Structured reason for `not_ready`. Matches Rust
 * `retrieval::NotReadyReason`; wire form is the snake_case `kind` tag
 * + variant fields. */
export type NotReadyReason =
  | { kind: "provider_unreachable"; detail: string }
  | { kind: "model_not_installed"; model: string }
  | { kind: "policy_denied" }
  | { kind: "embed_failed"; detail: string }
  | { kind: "bailout" }
  | { kind: "low_disk"; needed_gb: number; available_gb: number };

/** ADR-0007 D3 readiness state machine. Matches Rust
 * `retrieval::ReadinessState`. UI branches on `kind` to decide
 * whether to render the Trust-drawer indicator as ready, off, or
 * not-ready-with-reason. */
export type ReadinessState =
  | { kind: "unknown" }
  | { kind: "disabled" }
  | { kind: "ready" }
  | { kind: "not_ready"; reason: NotReadyReason };
