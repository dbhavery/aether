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
  | "draft_only";

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
