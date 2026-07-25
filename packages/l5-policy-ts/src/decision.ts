// Decision / Capability / Approval shapes — mirror of packages/l5-policy/src/*.
// Locked by DECISION_LOCK_PASS_2026-04-18c.md (Decisions 1, 2, 3, 4, 5).

// ---------- Common ids (opaque strings from Rust newtypes) ----------
export type RequestId = string;
export type TurnId = string;
export type TaskId = string;
export type SessionId = string;
export type PersonaId = string;
export type PresetId = string;
export type ChangeId = string;
export type GrantId = string;
export type AuditId = string;
export type ApprovalTicketId = string;
export type ProviderId = string;
export type IntegrationId = string;
export type ApiId = string;
export type AutomationId = string;
export type Cents = number;
export type MonotonicTimestamp = number;

// ---------- Capability (Decision 3 additions included) ----------
export type Capability =
  | { kind: "FilesRead" } | { kind: "FilesCreate" } | { kind: "FilesEdit" }
  | { kind: "FilesRenameMove" } | { kind: "FilesDelete" } | { kind: "FilesBulkOp" }
  | { kind: "BrowserOpen" } | { kind: "BrowserReadPage" } | { kind: "BrowserExtractData" }
  | { kind: "BrowserFillForm" } | { kind: "BrowserUpload" } | { kind: "BrowserDownload" }
  | { kind: "BrowserSubmit" } | { kind: "BrowserLoginReuse" }
  | { kind: "EmailReadMetadata" } | { kind: "EmailReadBody" } | { kind: "EmailDraft" }
  | { kind: "EmailEditDraft" } | { kind: "EmailSend" } | { kind: "EmailAttachmentAccess" }
  | { kind: "ClipboardRead" } | { kind: "ClipboardWrite" } | { kind: "ShellExec" }
  | { kind: "PackageInstall" } | { kind: "NotificationRead" } | { kind: "AutomationTrigger" }
  | { kind: "MemoryRead" } | { kind: "MemoryWriteSession" } | { kind: "MemoryWriteDurable" }
  | { kind: "MemoryWriteExtractedPref" } | { kind: "MemoryUseInFutureTask" }
  | { kind: "MemoryExport" } | { kind: "MemoryDelete" }
  | { kind: "MediaMic" } | { kind: "MediaCamera" } | { kind: "MediaScreenCapture" }
  | { kind: "IntegrationUse"; id: IntegrationId }
  | { kind: "IntegrationExternalApi"; id: ApiId }
  | { kind: "IntegrationTriggerAutomation"; id: AutomationId }
  | { kind: "RouterEscalateRemote" } | { kind: "RouterOverrideTier" }
  | { kind: "RouterAllowRemoteWithPrivate" }
  | { kind: "CostCapAdmin" }   // Decision 3 (2026-04-18)
  | { kind: "AuditExport" };   // Decision 3 (2026-04-18)

export type CapabilityPath = string;

export type RiskClass = "Low" | "Medium" | "High" | "Critical";

export type ResourceScope =
  | { kind: "None" }
  | { kind: "Path"; path: string }
  | { kind: "Url"; url: string }
  | { kind: "Mailbox"; address: string }
  | { kind: "Integration"; descriptor: string }
  | { kind: "CostScope"; provider: string; window: string };

export type ProvenanceTag =
  | "Public" | "Session" | "Durable" | "Private"
  | "UntrustedInput" | "ScrapedContent" | "ExtractedPreference";

// ---------- Approval / grant ----------
export type ApprovalMode = "Auto" | "TaskScoped" | "Ask" | "DraftOnly" | "Deny";

export type GrantDuration =
  | { tag: "Once" }
  | { tag: "TaskScoped"; task_id: TaskId }
  | { tag: "Session" }
  | { tag: "Persistent"; ttl_ns?: number };

/** Decision 2 (2026-04-18) — user choice includes DeferToDraft. */
export type UserChoice =
  | { tag: "Allow" }
  | { tag: "AllowScope"; scope: ResourceScope }
  | { tag: "AllowTask" }
  | { tag: "AllowSession" }
  | { tag: "Deny" }
  | { tag: "DeferToDraft" };

export interface ApprovalTicket {
  ticket_id: ApprovalTicketId;
  request_id: RequestId;
  capability: Capability;
  resource: ResourceScope;
  deadline_hint?: MonotonicTimestamp;
  suggested_duration?: GrantDuration;
}

export interface ApprovalResponse {
  ticket_id: ApprovalTicketId;
  user_choice: UserChoice;
  responded_at: MonotonicTimestamp;
  scope_override?: ResourceScope;
  duration_override?: GrantDuration;
  reauth_token?: { token: string; expires_at: MonotonicTimestamp };
}

// ---------- Decision (Decisions 1 + 2) ----------
/** Decision 2 — DraftOnly is discriminated by its source field. */
export type DraftSource = "System" | "UserChoice";

export type Decision =
  | { tag: "Allow"; grant_ref?: GrantId; audit_id: AuditId }
  | { tag: "Ask"; ticket: ApprovalTicket; audit_id: AuditId }
  | { tag: "DraftOnly"; audit_id: AuditId; source: DraftSource; reason?: string }
  | { tag: "Deny"; reason: DenyReason; audit_id: AuditId }
  /** Decision 1 (2026-04-18) — NeedsUpgrade is top-level, peer to Deny. */
  | { tag: "NeedsUpgrade";
      capability_path: CapabilityPath;
      audit_id: AuditId;
      suggested_preset?: PresetId };

export type DenyReason =
  | { kind: "HardcodedBlock"; id: string }
  | { kind: "FeatureDisabled" }
  | { kind: "ActionOutOfScope" }
  | { kind: "ResourceOutOfScope" }
  | { kind: "ModeDeny" }
  | { kind: "GrantExpired" }
  | { kind: "GrantRevoked" }
  | { kind: "ProvenanceTaint"; taint: "UntrustedInput" | "PrivateRemote"
                                       | "ScrapedHighRisk" | "LowConfidencePreference" }
  | { kind: "PrivacyPostureViolation" }
  | { kind: "CostCapHit"; provider: ProviderId }
  | { kind: "TierDowngradeStripped" }
  | { kind: "LedgerCorrupt" }
  | { kind: "AuditWriteFailed" };

export type DecisionKind =
  | "Allow" | "Ask" | "DraftOnlySystem" | "DraftOnlyUserChoice"
  | "Deny" | "NeedsUpgrade";

// ---------- Degraded mode / posture ----------
export type DegradedMode = "SafeMode" | "AuditBroken" | "LedgerCorrupt" | "MinimumTrust";
export type PrivacyPosture = "Strict" | "Balanced" | "Open";
export type PostureTrigger =
  | "PresetSwitch" | "PersonaSwap" | "DegradedEntry"
  | "DegradedExit" | "CapBlocklistUpdate";

// ---------- Decision 4: the 8 re-eval triggers ----------
export type ReEvalTrigger =
  | "CapabilityDiffers" | "ResourceOutsidePattern" | "PersonaSwapped"
  | "RemoteEscalationUncovered" | "ProvenanceElevated" | "CostThresholdHit"
  | "GrantOrEmergencyRevoked" | "TtlExpired";

export const RE_EVAL_TRIGGERS: readonly ReEvalTrigger[] = [
  "CapabilityDiffers", "ResourceOutsidePattern", "PersonaSwapped",
  "RemoteEscalationUncovered", "ProvenanceElevated", "CostThresholdHit",
  "GrantOrEmergencyRevoked", "TtlExpired",
] as const;

// Note: `PolicyIpcError` is defined in ./support.ts (mirrors the Rust `ipc`
// module). Avoid duplicating it here to keep a single canonical export.
