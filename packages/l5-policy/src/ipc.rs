//! Tauri IPC command surface (16 commands).
//!
//! 13 base commands from L5_interface_pack.md §6.2 +
//! 3 additions locked by Decision 3 (2026-04-18):
//!   - `policy.export_audit`
//!   - `policy.set_cost_cap`
//!   - `policy.reset_cost_counter`
//!
//! Wave 2 exposes a `PolicyCommands` trait with the full signature surface.
//! No handler implementation. The Tauri `invoke_handler!` wire-up lands with
//! `apps/desktop/` in a later wave.

use serde::{Deserialize, Serialize};

use crate::approval::{ApprovalResponse, ApprovalTicket};
use crate::audit::{AuditFilter, AuditRecordEvent, AuditSummary};
use crate::byok::{CostCap, CostWindow, ProviderId};
use crate::capability::{CapabilityFilter, CapabilityInfo};
use crate::common::{ChangeId, PresetId, RequestId};
use crate::decision::Decision;
use crate::events::{EmergencyScope, GrantRevokedEvent};
use crate::grants::{Grant, GrantFilter};
use crate::policy_engine::ActionRequest;
use crate::posture::DegradedMode;

/// Format options for `policy.export_audit`.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum AuditExportFormat {
    /// Newline-delimited JSON.
    Ndjson,
    /// CSV.
    Csv,
}

/// Uri wrapper for exported artifacts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportUri(pub String);

/// Receipt for an approved approval response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalReceipt {
    /// The change-id cluster started by this response.
    pub change_id: ChangeId,
}

/// Receipt for a preset-switch command.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PresetSwitchReceipt {
    /// New preset.
    pub preset: PresetId,
    /// Grants stripped during narrow, if any.
    pub stripped_count: u32,
}

/// Current preset snapshot.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentPreset {
    /// Active preset id.
    pub preset: PresetId,
    /// Version.
    pub version: u32,
}

/// Target of a revoke command.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RevokeTarget {
    /// Single grant.
    Grant(crate::grants::GrantId),
    /// All grants for a capability.
    Capability(crate::capability::Capability),
    /// Every grant held by a persona.
    Persona(crate::common::PersonaId),
    /// Every active grant.
    All,
}

/// Receipt for `policy.revoke`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RevokeReceipt {
    /// Grants revoked.
    pub revoked: Vec<GrantRevokedEvent>,
}

/// Receipt for `policy.emergency_revoke_all`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmergencyReceipt {
    /// Completion time (monotonic ns).
    pub completed_ns: u64,
    /// Revoked count.
    pub revoked_count: u32,
}

/// Human-readable explanation of a decision (for trust-center drilldown).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Explanation {
    /// Decision kind.
    pub decision: Decision,
    /// Ordered stage trace in human terms.
    pub stages: Vec<String>,
}

/// Output of `policy.preview_plan`. Shape only; scope P1 vs P2 is flagged open
/// in L5_interface_pack.md §10 item 9.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanPreview {
    /// Per-step projected decisions.
    pub steps: Vec<Decision>,
    /// Whether the preview is best-effort only.
    pub advisory: bool,
}

/// Cursor opaque to callers (server-side pagination).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamCursor(pub String);

/// Complete IPC surface — every `invoke` the webview may call.
///
/// Implementations live in `apps/desktop/src-tauri/` once scaffolded.
/// Wave 2 only defines the trait.
pub trait PolicyCommands: Send + Sync {
    // --- Base catalog (13) ---
    /// Evaluate an action request synchronously.
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyIpcError>;
    /// Fetch a ticket for a pending request id.
    fn request_approval(&self, request_id: RequestId) -> Result<ApprovalTicket, PolicyIpcError>;
    /// Submit a user response to a pending ticket.
    fn respond_approval(
        &self,
        response: ApprovalResponse,
    ) -> Result<ApprovalReceipt, PolicyIpcError>;
    /// Switch preset. Gated behind re-auth.
    fn set_preset(&self, preset: PresetId) -> Result<PresetSwitchReceipt, PolicyIpcError>;
    /// Read current preset.
    fn get_preset(&self) -> Result<CurrentPreset, PolicyIpcError>;
    /// List live grants.
    fn list_grants(&self, filter: GrantFilter) -> Result<Vec<Grant>, PolicyIpcError>;
    /// Revoke one or more grants.
    fn revoke(&self, target: RevokeTarget) -> Result<RevokeReceipt, PolicyIpcError>;
    /// Enumerate capabilities (filtered by active posture).
    fn list_capabilities(
        &self,
        filter: CapabilityFilter,
    ) -> Result<Vec<CapabilityInfo>, PolicyIpcError>;
    /// Explain a single decision by audit id.
    fn explain_decision(
        &self,
        audit_id: crate::audit::AuditId,
    ) -> Result<Explanation, PolicyIpcError>;
    /// Preview a plan of action requests (P1/P2 scope open).
    fn preview_plan(&self, plan: Vec<ActionRequest>) -> Result<PlanPreview, PolicyIpcError>;
    /// Big-red-button emergency revoke.
    fn emergency_revoke_all(
        &self,
        scope: EmergencyScope,
    ) -> Result<EmergencyReceipt, PolicyIpcError>;
    /// Paginated audit summary.
    fn get_audit_summary(&self, filter: AuditFilter) -> Result<Vec<AuditSummary>, PolicyIpcError>;
    /// Streaming audit cursor — Wave 3 will replace `Vec` with an async stream.
    fn stream_audit(
        &self,
        filter: AuditFilter,
        cursor: Option<StreamCursor>,
    ) -> Result<Vec<AuditRecordEvent>, PolicyIpcError>;

    // --- Decision 3 additions (2026-04-18) ---

    /// Export audit log for a filter window. Capability: `AuditExport`, re-auth required.
    fn export_audit(
        &self,
        filter: AuditFilter,
        format: AuditExportFormat,
    ) -> Result<ExportUri, PolicyIpcError>;

    /// Set a BYOK cost cap for `(provider, window)`. Capability: `CostCapAdmin`, re-auth required.
    fn set_cost_cap(
        &self,
        provider: ProviderId,
        window: CostWindow,
        cap: CostCap,
    ) -> Result<ChangeId, PolicyIpcError>;

    /// Reset a BYOK cost counter for `(provider, window)`. Capability: `CostCapAdmin`, re-auth required.
    fn reset_cost_counter(
        &self,
        provider: ProviderId,
        window: CostWindow,
    ) -> Result<ChangeId, PolicyIpcError>;
}

/// IPC-visible error shape. Stable `code` string for TS interop.
#[derive(Debug, Clone, thiserror::Error, Serialize, Deserialize)]
#[serde(tag = "code", rename_all = "snake_case")]
pub enum PolicyIpcError {
    /// Engine is in a degraded mode.
    #[error("degraded mode: {mode:?}")]
    Degraded {
        /// Active degraded mode.
        mode: DegradedMode,
    },
    /// Command required a re-auth `CommandToken` and none / expired was presented.
    #[error("requires re-auth")]
    RequiresReauth,
    /// Ticket / grant / audit id not found.
    #[error("not found: {msg}")]
    NotFound {
        /// Detail.
        msg: String,
    },
    /// Invalid payload (unknown capability, malformed scope, stale timestamp, ...).
    #[error("invalid: {msg}")]
    Invalid {
        /// Detail.
        msg: String,
    },
    /// Conflict (double-response, concurrent emergency-revoke, stale ticket).
    #[error("conflict: {msg}")]
    Conflict {
        /// Detail.
        msg: String,
    },
    /// Audit writer unhealthy; deny-all in effect.
    #[error("audit blocked")]
    AuditBlocked,
    /// Uncategorized error.
    #[error("internal: {msg}")]
    Internal {
        /// Detail.
        msg: String,
    },
}
