// Tauri IPC command surface — 16 commands (13 base + 3 from Decision 3).
// Hand-written mirror of packages/l5-policy/src/ipc.rs. The handler
// implementation lives in apps/desktop/src-tauri (future wave).

import type {
  ActionRequest,
  ApprovalReceipt,
  AuditExportFormat,
  AuditFilter,
  AuditRecordEvent,
  AuditSummary,
  CapabilityFilter,
  CapabilityInfo,
  CostCap,
  CostWindow,
  CurrentPreset,
  EmergencyReceipt,
  EmergencyScope,
  ExportUri,
  Explanation,
  Grant,
  GrantFilter,
  PlanPreview,
  PolicyIpcError,
  PresetSwitchReceipt,
  RevokeReceipt,
  RevokeTarget,
  StreamCursor,
} from "./support.js";
import type {
  ApprovalResponse,
  ApprovalTicket,
  AuditId,
  ChangeId,
  Decision,
  PresetId,
  ProviderId,
  RequestId,
} from "./decision.js";

/** Full IPC surface exposed to the webview via Tauri `invoke`. */
export interface PolicyCommands {
  // --- Base catalog (13) ---
  "policy.evaluate":            (req: ActionRequest) => Promise<Decision>;
  "policy.request_approval":    (req: { request_id: RequestId }) => Promise<ApprovalTicket>;
  "policy.respond_approval":    (req: ApprovalResponse) => Promise<ApprovalReceipt>;
  "policy.set_preset":          (req: { preset: PresetId }) => Promise<PresetSwitchReceipt>;
  "policy.get_preset":          () => Promise<CurrentPreset>;
  "policy.list_grants":         (req: { filter?: GrantFilter }) => Promise<Grant[]>;
  "policy.revoke":              (req: { target: RevokeTarget }) => Promise<RevokeReceipt>;
  "policy.list_capabilities":   (req: { filter?: CapabilityFilter }) => Promise<CapabilityInfo[]>;
  "policy.explain_decision":    (req: { audit_id: AuditId }) => Promise<Explanation>;
  "policy.preview_plan":        (req: { plan: ActionRequest[] }) => Promise<PlanPreview>;
  "policy.emergency_revoke_all":(req: { scope: EmergencyScope }) => Promise<EmergencyReceipt>;
  "policy.get_audit_summary":   (req: { filter: AuditFilter }) => Promise<AuditSummary[]>;
  "policy.stream_audit":
    (req: { filter: AuditFilter; cursor?: StreamCursor }) => Promise<AuditRecordEvent[]>;

  // --- Decision 3 additions (2026-04-18) ---
  "policy.export_audit":
    (req: { filter: AuditFilter; format: AuditExportFormat }) => Promise<ExportUri>;
  "policy.set_cost_cap":
    (req: { provider: ProviderId; window: CostWindow; cap: CostCap }) => Promise<ChangeId>;
  "policy.reset_cost_counter":
    (req: { provider: ProviderId; window: CostWindow }) => Promise<ChangeId>;
}

/** Typed error shape returned by any command. */
export type { PolicyIpcError };
