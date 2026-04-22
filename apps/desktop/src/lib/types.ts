// Types mirroring the Rust command payloads. Hand-maintained for v0;
// a `ts-rs` codegen pass can replace this once the command surface
// stabilises (see planning/plans/X3_tauri_architecture.md §2.3).

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
  /** Vision-route model id, when the assistant message came from a
   * vision provider that exposes one. Mirrors `TelemetryEntry.model`
   * so transcript bubbles, the per-panel hint, and the Trust drawer
   * all show the same identifier for the same turn. Absent for
   * text-only turns and for adapters that don't report a model. */
  model?: string;
  // Optional because the Rust side `#[serde(skip_serializing_if = "Option::is_none")]`
  // drops these fields when absent; treat missing as "not reported".
  latency_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
}

export interface TranscriptMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sequence: number;
  timestamp_ms: number;
  meta: MessageMeta | null;
}

export interface ApprovalPayload {
  ticket_id: string;
  capability: string;
  scope: string;
  reason: string;
  risk_hint: string;
}

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

export interface TrustAuditRow {
  audit_id: string;
  decision: AuditDecisionLabel;
  capability: string;
  scope: string;
  change_id: string;
  at_mono_ns: number;
  at_epoch_s: number;
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
