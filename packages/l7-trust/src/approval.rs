//! Wave L7.1 — minimal approval surface.
//!
//! Turns an in-flight L5 `Decision::Ask` into a simple accept/reject loop
//! that the current CLI / demo path can drive. This is deliberately not the
//! full trust centre:
//!
//! - two outcomes only (approve once / reject),
//! - per-ticket, not broad permanent grants,
//! - a synchronous trait so any caller (stdin REPL, scripted test, later a
//!   real desktop bridge) can supply the user decision.
//!
//! Richer UX (duration pickers, scope narrowing, defer-to-draft, audit
//! surfacing, re-auth prompts) is intentionally out of scope here — the
//! building blocks exist in [`aether_l5_policy::UserChoice`] and can be wired
//! in later without reshaping this trait.
//!
//! The existing [`ApprovalPrompt`](crate::ApprovalPrompt) shape is reused for
//! the render payload; only the resolution trait + concrete surfaces live in
//! this module.

use std::io::{self, BufRead, Write};

use aether_l5_policy::{
    ApprovalResponse, ApprovalTicket, Capability, MonotonicTimestamp, ResourceScope,
    StaticReasonId, UserChoice,
};
use serde::{Deserialize, Serialize};

use crate::error::L7Error;
use crate::shell::ApprovalPrompt;

/// Outcome of showing an [`ApprovalPrompt`] to a user. L7.1 keeps this
/// deliberately narrow — broader choices (scope override, deferred draft,
/// session grant) map to [`UserChoice`] and can be surfaced without breaking
/// this type: add a variant here and update [`resolution_to_user_choice`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ApprovalResolution {
    /// Approve once for this ticket. Maps to [`UserChoice::Allow`].
    Approve,
    /// Reject. Maps to [`UserChoice::Deny`].
    Reject,
}

/// Narrow approval-surface contract. A caller presents an
/// [`ApprovalPrompt`] and blocks until the user picks a resolution.
///
/// Implementations must be cheap to call on the engine thread — the demo/CLI
/// drives this synchronously from its turn loop. A future async/streaming
/// variant can sit beside this without replacing it.
pub trait ApprovalSurface: Send + Sync {
    /// Render `prompt` and return the user's resolution.
    fn resolve(&self, prompt: &ApprovalPrompt) -> Result<ApprovalResolution, L7Error>;
}

/// Map a minimal [`ApprovalResolution`] onto the richer
/// [`UserChoice`](aether_l5_policy::UserChoice) surface consumed by
/// `PolicyEngine::respond_approval`.
pub fn resolution_to_user_choice(r: ApprovalResolution) -> UserChoice {
    match r {
        ApprovalResolution::Approve => UserChoice::Allow,
        ApprovalResolution::Reject => UserChoice::Deny,
    }
}

/// Build an [`ApprovalResponse`] from a resolution + originating ticket.
/// Leaves scope/duration/reauth overrides unset — L7.1 keeps approvals
/// scoped tightly to the ticket that issued them.
pub fn build_approval_response(
    ticket: &ApprovalTicket,
    resolution: ApprovalResolution,
    responded_at: MonotonicTimestamp,
) -> ApprovalResponse {
    ApprovalResponse {
        ticket_id: ticket.ticket_id.clone(),
        user_choice: resolution_to_user_choice(resolution),
        responded_at,
        scope_override: None,
        duration_override: None,
        reauth_token: None,
    }
}

/// Build a renderable [`ApprovalPrompt`] from a ticket. The `reason` is a
/// stable reason id — L7.1 uses `"approval_required"` by default; callers
/// that already have a more specific id (e.g. from an `ApprovalPendingEvent`)
/// can pass it through.
pub fn approval_prompt_from_ticket(
    ticket: ApprovalTicket,
    reason: Option<StaticReasonId>,
) -> ApprovalPrompt {
    let capability = ticket.capability.clone();
    let resource = ticket.resource.clone();
    ApprovalPrompt {
        ticket,
        capability,
        resource,
        reason: reason.unwrap_or_else(|| StaticReasonId(String::from("approval_required"))),
    }
}

/// Deterministic, stable label for a `Capability` variant. Used by the CLI
/// surface and by tests that assert against the rendered prompt. Not an
/// exhaustive UI copy table — just what L7.1 needs to render sensibly.
pub fn human_capability(cap: &Capability) -> &'static str {
    match cap {
        Capability::FilesRead => "files.read",
        Capability::FilesCreate => "files.create",
        Capability::FilesEdit => "files.edit",
        Capability::FilesRenameMove => "files.rename_move",
        Capability::FilesDelete => "files.delete",
        Capability::FilesBulkOp => "files.bulk_op",
        Capability::BrowserOpen => "browser.open",
        Capability::BrowserReadPage => "browser.read_page",
        Capability::BrowserExtractData => "browser.extract_data",
        Capability::BrowserFillForm => "browser.fill_form",
        Capability::BrowserUpload => "browser.upload",
        Capability::BrowserDownload => "browser.download",
        Capability::BrowserSubmit => "browser.submit",
        Capability::BrowserLoginReuse => "browser.login_reuse",
        Capability::EmailReadMetadata => "email.read_metadata",
        Capability::EmailReadBody => "email.read_body",
        Capability::EmailDraft => "email.draft",
        Capability::EmailEditDraft => "email.edit_draft",
        Capability::EmailSend => "email.send",
        Capability::EmailAttachmentAccess => "email.attachment_access",
        Capability::ClipboardRead => "clipboard.read",
        Capability::ClipboardWrite => "clipboard.write",
        Capability::ShellExec => "shell.exec",
        Capability::PackageInstall => "package.install",
        Capability::NotificationRead => "notification.read",
        Capability::AutomationTrigger => "automation.trigger",
        Capability::MemoryRead => "memory.read",
        Capability::MemoryWriteSession => "memory.write_session",
        Capability::MemoryWriteDurable => "memory.write_durable",
        Capability::MemoryWriteExtractedPref => "memory.write_extracted_pref",
        Capability::MemoryUseInFutureTask => "memory.use_in_future_task",
        Capability::MemoryExport => "memory.export",
        Capability::MemoryDelete => "memory.delete",
        Capability::MemoryWrite => "memory.write",
        Capability::MemoryForget => "memory.forget",
        Capability::MemoryEdit => "memory.edit",
        Capability::MemoryEmbed => "memory.embed",
        Capability::RetrievalContext => "retrieval_context",
        Capability::MediaMic => "media.mic",
        Capability::MediaCamera => "media.camera",
        Capability::MediaScreenCapture => "media.screen_capture",
        Capability::IntegrationUse(_) => "integration.use",
        Capability::IntegrationExternalApi(_) => "integration.external_api",
        Capability::IntegrationTriggerAutomation(_) => "integration.trigger_automation",
        Capability::RouterEscalateRemote => "router.escalate_remote",
        Capability::RouterOverrideTier => "router.override_tier",
        Capability::RouterAllowRemoteWithPrivate => "router.allow_remote_with_private",
        Capability::CostCapAdmin => "cost_cap.admin",
        Capability::AuditExport => "audit.export",
        Capability::PersonaDownload => "persona.download",
        Capability::PersonaInstall => "persona.install",
        Capability::PersonaUninstall => "persona.uninstall",
        Capability::PersonaSwitch => "persona.switch",
    }
}

/// Human-readable scope string for prompt rendering.
pub fn human_scope(scope: &ResourceScope) -> String {
    match scope {
        ResourceScope::None => "(no specific resource)".to_string(),
        ResourceScope::Path(p) => format!("path: {p}"),
        ResourceScope::Url(u) => format!("url: {u}"),
        ResourceScope::Mailbox(m) => format!("mailbox: {m}"),
        ResourceScope::Integration(i) => format!("integration: {i}"),
        ResourceScope::CostScope { provider, window } => {
            format!("cost: provider={provider}, window={window}")
        }
    }
}

/// Render a multi-line approval block for a terminal UI. Deterministic so
/// tests can assert against it.
pub fn render_approval_block(prompt: &ApprovalPrompt) -> String {
    format!(
        "Approval required:\n  ticket     : {}\n  capability : {}\n  scope      : {}\n  reason     : {}\n",
        prompt.ticket.ticket_id.0,
        human_capability(&prompt.capability),
        human_scope(&prompt.resource),
        prompt.reason.0,
    )
}

/// Trait-object friendly CLI surface. Writes the rendered prompt to stdout
/// and reads a single line from stdin; accepts `y`, `yes`, `approve`, `a`
/// (case-insensitive) as approval; anything else is rejection.
///
/// The one test that drives this directly is in the demo crate — here we
/// stick to the default types so the core crate stays I/O-thin.
pub struct CliApprovalSurface;

impl CliApprovalSurface {
    /// New surface.
    pub fn new() -> Self {
        Self
    }

    /// Parse a single user line into a resolution. `y`, `yes`, `approve`,
    /// `a` → approve (case-insensitive, trimmed). Any other input → reject.
    pub fn parse_line(line: &str) -> ApprovalResolution {
        match line.trim().to_ascii_lowercase().as_str() {
            "y" | "yes" | "approve" | "a" => ApprovalResolution::Approve,
            _ => ApprovalResolution::Reject,
        }
    }
}

impl Default for CliApprovalSurface {
    fn default() -> Self {
        Self::new()
    }
}

impl ApprovalSurface for CliApprovalSurface {
    fn resolve(&self, prompt: &ApprovalPrompt) -> Result<ApprovalResolution, L7Error> {
        let block = render_approval_block(prompt);
        let stdout = io::stdout();
        let mut out = stdout.lock();
        let _ = out.write_all(block.as_bytes());
        let _ = out.write_all(b"Approve? [y/N]: ");
        let _ = out.flush();

        let stdin = io::stdin();
        let mut line = String::new();
        stdin
            .lock()
            .read_line(&mut line)
            .map_err(|e| L7Error::Internal(format!("stdin read failed: {e}")))?;
        Ok(Self::parse_line(&line))
    }
}

/// Test double that always returns a fixed resolution. Useful for unit tests
/// that exercise the approval loop without touching the terminal.
pub struct FixedApprovalSurface(pub ApprovalResolution);

impl ApprovalSurface for FixedApprovalSurface {
    fn resolve(&self, _prompt: &ApprovalPrompt) -> Result<ApprovalResolution, L7Error> {
        Ok(self.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aether_l5_policy::{
        ApprovalTicket, ApprovalTicketId, Capability, RequestId, ResourceScope,
    };

    fn ticket() -> ApprovalTicket {
        ApprovalTicket {
            ticket_id: ApprovalTicketId("t-1".to_string()),
            request_id: RequestId("r-1".to_string()),
            capability: Capability::FilesCreate,
            resource: ResourceScope::Path("/tmp/foo".to_string()),
            deadline_hint: None,
            suggested_duration: None,
        }
    }

    #[test]
    fn resolution_maps_to_user_choice() {
        matches!(
            resolution_to_user_choice(ApprovalResolution::Approve),
            UserChoice::Allow
        );
        matches!(
            resolution_to_user_choice(ApprovalResolution::Reject),
            UserChoice::Deny
        );
    }

    #[test]
    fn build_response_echoes_ticket_id_and_choice() {
        let t = ticket();
        let r = build_approval_response(&t, ApprovalResolution::Approve, MonotonicTimestamp(42));
        assert_eq!(r.ticket_id.0, "t-1");
        assert!(matches!(r.user_choice, UserChoice::Allow));
        assert_eq!(r.responded_at.0, 42);
        assert!(r.scope_override.is_none());
        assert!(r.duration_override.is_none());
    }

    #[test]
    fn prompt_from_ticket_copies_fields_and_defaults_reason() {
        let p = approval_prompt_from_ticket(ticket(), None);
        assert!(matches!(p.capability, Capability::FilesCreate));
        assert_eq!(p.reason.0, "approval_required");
    }

    #[test]
    fn prompt_from_ticket_honours_explicit_reason() {
        let p = approval_prompt_from_ticket(
            ticket(),
            Some(StaticReasonId("file_mutation".to_string())),
        );
        assert_eq!(p.reason.0, "file_mutation");
    }

    #[test]
    fn render_approval_block_contains_all_fields() {
        let p = approval_prompt_from_ticket(ticket(), None);
        let block = render_approval_block(&p);
        assert!(block.contains("ticket"));
        assert!(block.contains("t-1"));
        assert!(block.contains("files.create"));
        assert!(block.contains("/tmp/foo"));
        assert!(block.contains("approval_required"));
    }

    #[test]
    fn cli_parse_accepts_affirmative_variants() {
        for y in ["y", "Y", "yes", "YES", "approve", " A ", "Approve\n"] {
            assert_eq!(
                CliApprovalSurface::parse_line(y),
                ApprovalResolution::Approve,
                "expected approve for {y:?}",
            );
        }
    }

    #[test]
    fn cli_parse_rejects_anything_else() {
        for n in ["n", "no", "N", "", " ", "reject", "maybe", "1"] {
            assert_eq!(
                CliApprovalSurface::parse_line(n),
                ApprovalResolution::Reject,
                "expected reject for {n:?}",
            );
        }
    }

    #[test]
    fn fixed_surface_returns_configured_resolution() {
        let p = approval_prompt_from_ticket(ticket(), None);
        let s = FixedApprovalSurface(ApprovalResolution::Approve);
        assert_eq!(s.resolve(&p).unwrap(), ApprovalResolution::Approve);
        let s = FixedApprovalSurface(ApprovalResolution::Reject);
        assert_eq!(s.resolve(&p).unwrap(), ApprovalResolution::Reject);
    }
}
