// Support types referenced by commands.ts. Kept separate from decision.ts
// to mirror the Rust module boundaries and make the generator replacement
// in Wave 2+ cleaner.
//
// Every type here is a hand-written mirror of a Rust struct or enum in
// packages/l5-policy/src/ and will be regenerated once ts-rs lands.

import type {
  ApprovalTicket,
  AuditId,
  Capability,
  CapabilityPath,
  Cents,
  ChangeId,
  Decision,
  DecisionKind,
  DegradedMode,
  GrantDuration,
  GrantId,
  MonotonicTimestamp,
  PersonaId,
  PresetId,
  PrivacyPosture,
  ProviderId,
  RequestId,
  ResourceScope,
  RiskClass,
  TaskId,
  TurnId,
} from "./decision.js";

// ---------- ActionRequest ----------
export interface ActionRequest {
  request_id: RequestId;
  turn_id: TurnId;
  capability: Capability;
  resource: ResourceScope;
  actor_persona: PersonaId;
  emitted_at: MonotonicTimestamp;
  task_id?: TaskId;
  provenance_tags: string[];          // ProvenanceTag union, stringly at IPC edge
  intended_route?: "LocalOnly" | "LocalPreferred" | "RemoteEscalation";
  risk_class_hint?: RiskClass;
}

// ---------- Grant ----------
export interface Grant {
  grant_id: GrantId;
  capability: Capability;
  resource_pattern: ResourceScope;
  persona_id: PersonaId;
  approval_mode: "Auto" | "TaskScoped" | "Ask" | "DraftOnly" | "Deny";
  duration: GrantDuration;
  issued_at: MonotonicTimestamp;
  expires_at?: MonotonicTimestamp;
  preset_version_issued_under: number;
}

export interface GrantFilter {
  active_only?: boolean;
  persona_id?: PersonaId;
  capability?: Capability;
}

export interface CapabilityFilter {
  only_enabled?: boolean;
  only_persona_scoped?: boolean;
}

export interface CapabilityInfo {
  capability: Capability;
  label: string;
  risk_class: RiskClass;
  has_active_grant: boolean;
  as_of: MonotonicTimestamp;
}

// ---------- Audit ----------
export interface AuditFilter {
  capability_prefix?: string;
  persona_id?: PersonaId;
  since?: MonotonicTimestamp;
  until?: MonotonicTimestamp;
  decisions?: DecisionKind[];
}

export interface AuditSummary {
  window: [MonotonicTimestamp, MonotonicTimestamp];
  by_decision: Record<DecisionKind, number>;
  top_capabilities: [Capability, number][];
}

export interface AuditRecordEvent {
  audit_id: AuditId;
  timestamp_monotonic: MonotonicTimestamp;
  timestamp_wall: { epoch_s: number; ns: number };
  capability: Capability;
  resource: ResourceScope;
  decision: DecisionKind;
  change_id: ChangeId;
  prev_hash: number[];
  record_hmac: number[];
  key_id: string;
  seq: number;
  reason?: string;
  privileged_profile: boolean;
}

// ---------- Posture / presets ----------
export interface CurrentPreset { preset: PresetId; version: number; }
export interface PresetSwitchReceipt { preset: PresetId; stripped_count: number; }
export interface PolicyPostureSummary {
  preset: PresetId;
  preset_version: number;
  persona_id: PersonaId;
  persona_version: number;
  privacy_posture: PrivacyPosture;
  degraded?: DegradedMode;
  hash: number;
}

// ---------- Revoke / emergency ----------
export type RevokeTarget =
  | { kind: "Grant"; grant_id: GrantId }
  | { kind: "Capability"; capability: Capability }
  | { kind: "Persona"; persona_id: PersonaId }
  | { kind: "All" };

export interface RevokeReceipt {
  revoked: { grant_id: GrantId; revoked_at: MonotonicTimestamp }[];
}

export type EmergencyScope =
  | { kind: "All" }
  | { kind: "Category"; capability: Capability }
  | { kind: "Persona"; persona_id: PersonaId };

export interface EmergencyReceipt {
  completed_ns: number;
  revoked_count: number;
}

// ---------- BYOK / cost ----------
export type CostWindow =
  | { kind: "Daily" }
  | { kind: "Monthly" }
  | { kind: "Session" }
  | { kind: "PerPersona"; persona_id: PersonaId };

export interface CostCap {
  cents: Cents;
  warn_at_pct?: number;
}

export type AuditExportFormat = "Ndjson" | "Csv";
export type ExportUri = string;

// ---------- Misc ----------
export type StreamCursor = string;

export interface Explanation {
  decision: Decision;
  stages: string[];
}

export interface PlanPreview {
  steps: Decision[];
  advisory: boolean;
}

/** Mirror of ipc::PolicyIpcError. */
export type PolicyIpcError =
  | { code: "degraded"; mode: DegradedMode }
  | { code: "requires_reauth" }
  | { code: "not_found"; msg: string }
  | { code: "invalid"; msg: string }
  | { code: "conflict"; msg: string }
  | { code: "audit_blocked" }
  | { code: "internal"; msg: string };

/** Mirror of ipc::ApprovalReceipt — separate from the Rust approval module. */
export interface ApprovalReceipt {
  change_id: ChangeId;
}

/** Tauri-command ticket relay. */
export type { ApprovalTicket };

// Pass-throughs so commands.ts does not import from decision.ts directly.
export type { CapabilityPath, PresetId, ProviderId, RequestId, ChangeId };
