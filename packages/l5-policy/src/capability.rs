//! Capability taxonomy and resource scopes.
//!
//! Source of truth:
//! - `planning/plans/L5_policy_engine_system_design.md` §2.1 & §2.2
//!   (7 capability groups, 45+ sub-capabilities; defaults table).
//! - `planning/plans/implementation_prep/L5_interface_pack.md` §6.1
//!   (Rust enum reference).
//! - `planning/DECISION_LOCK_PASS_2026-04-18c.md` Decision 3 —
//!   adds `CostCapAdmin` + `AuditExport` capabilities to the canonical enum.
//!
//! **Never stringly typed.** All consumers pattern-match on these enum
//! variants. Adding a new capability is a planning PR first (CLAUDE.md §3).

use serde::{Deserialize, Serialize};

use crate::common::MonotonicTimestamp;

/// Opaque id for a registered integration (e.g. an MCP server).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct IntegrationId(pub String);

/// Opaque id for an external API configured at integration time.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ApiId(pub String);

/// Opaque id for an automation trigger.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AutomationId(pub String);

/// Canonical capability taxonomy — 7 groups from L5 §2.1 plus the two
/// Decision 3 additions (`CostCapAdmin`, `AuditExport`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Capability {
    // ----- Files -----
    /// Read file contents within scope.
    FilesRead,
    /// Create new files within scope.
    FilesCreate,
    /// Edit existing files within scope.
    FilesEdit,
    /// Rename / move files within scope.
    FilesRenameMove,
    /// Delete files within scope.
    FilesDelete,
    /// Bulk file operations (archive, mass rename).
    FilesBulkOp,

    // ----- Browser -----
    /// Open a browser to a URL.
    BrowserOpen,
    /// Read page contents.
    BrowserReadPage,
    /// Extract structured data from a page.
    BrowserExtractData,
    /// Fill forms on a page.
    BrowserFillForm,
    /// Upload to a page.
    BrowserUpload,
    /// Download from a page.
    BrowserDownload,
    /// Submit a form / complete a transaction.
    BrowserSubmit,
    /// Reuse an existing authenticated session.
    BrowserLoginReuse,

    // ----- Email -----
    /// Read email metadata (subject, sender, headers).
    EmailReadMetadata,
    /// Read email body contents.
    EmailReadBody,
    /// Create a draft.
    EmailDraft,
    /// Edit an existing draft.
    EmailEditDraft,
    /// Send email.
    EmailSend,
    /// Access attachments.
    EmailAttachmentAccess,

    // ----- System & tools -----
    /// Read system clipboard.
    ClipboardRead,
    /// Write system clipboard.
    ClipboardWrite,
    /// Execute a shell command.
    ShellExec,
    /// Install a package.
    PackageInstall,
    /// Read OS notifications.
    NotificationRead,
    /// Trigger a configured automation.
    AutomationTrigger,

    // ----- Memory -----
    /// Read memory items.
    MemoryRead,
    /// Write session-scoped memory.
    MemoryWriteSession,
    /// Write durable memory.
    MemoryWriteDurable,
    /// Write an extracted preference memory.
    MemoryWriteExtractedPref,
    /// Carry a memory item into a future task.
    MemoryUseInFutureTask,
    /// Export memory.
    MemoryExport,
    /// Delete memory.
    MemoryDelete,

    // ----- Media -----
    /// Access microphone.
    MediaMic,
    /// Access camera.
    MediaCamera,
    /// Capture the screen.
    MediaScreenCapture,

    // ----- Integrations -----
    /// Use a registered integration.
    IntegrationUse(IntegrationId),
    /// Call a registered external API.
    IntegrationExternalApi(ApiId),
    /// Fire a registered automation.
    IntegrationTriggerAutomation(AutomationId),

    // ----- Router / cost -----
    /// Escalate to a remote model tier.
    RouterEscalateRemote,
    /// Override the persona's tier preference.
    RouterOverrideTier,
    /// Allow remote routing with private-tagged context (Strict gate override).
    RouterAllowRemoteWithPrivate,

    // ----- Admin (Decision 3 additions, 2026-04-18) -----
    /// Administer BYOK cost caps (set_cost_cap, reset_cost_counter).
    /// Critical; always Ask with re-auth.
    CostCapAdmin,
    /// Export the audit log (full or filtered). Critical; always Ask.
    AuditExport,
    // TODO(wave-3): `Capability::AuditExport` vs `Capability::MemoryExport`
    // distinction locked by Decision 3. Confirm L7 trust-center export UX
    // uses `AuditExport` for the audit export action, `MemoryExport` for the
    // memory export action. See L5_interface_pack.md §10 item 8.
}

/// Dot-path identifier for `Capability` variants used in `NeedsUpgrade` and
/// CLI / audit serialization.
///
/// This is an opaque wrapper for Wave 2. Real path canonicalization
/// (e.g. `"files.read"`) is a later-wave concern tied to preset authoring.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct CapabilityPath(pub String);

impl CapabilityPath {
    /// Stub — later waves canonicalize `Capability` → dot-path.
    pub fn for_capability(_cap: &Capability) -> Self {
        // TODO(wave-3): implement canonical dot-path derivation.
        CapabilityPath(String::from("unknown.path"))
    }
}

/// Resource scope a capability is bound to — typed per capability family.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ResourceScope {
    /// No resource (e.g. `BrowserOpen` with a URL carried elsewhere, or
    /// capabilities that are scope-less).
    None,
    /// Filesystem path (absolute or pattern).
    Path(String),
    /// URL or URL pattern.
    Url(String),
    /// Email address / mailbox.
    Mailbox(String),
    /// Integration-specific scope descriptor.
    Integration(String),
    /// Cost window scope for `CostCapAdmin` (provider + window).
    CostScope {
        /// Provider id.
        provider: String,
        /// Window identifier (see `byok::CostWindow`).
        window: String,
    },
}

/// Filter for `capabilities()` introspection queries.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CapabilityFilter {
    /// Only include capabilities currently enabled by the active preset.
    pub only_enabled: bool,
    /// Only include capabilities the active persona may request.
    pub only_persona_scoped: bool,
}

/// Static capability-metadata record returned by introspection.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityInfo {
    /// The capability itself.
    pub capability: Capability,
    /// Short human-readable label for UI.
    pub label: &'static str,
    /// Risk class (Low / Medium / High / Critical).
    pub risk_class: RiskClass,
    /// Whether an active grant exists right now for the default scope.
    pub has_active_grant: bool,
    /// Moment the info record was produced (for cache busting).
    pub as_of: MonotonicTimestamp,
}

/// Risk class lifted from L5 defaults table.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RiskClass {
    /// Low — local, non-destructive, non-costly.
    Low,
    /// Medium — local mutating or metadata-only external.
    Medium,
    /// High — external-effect, mutating, or costly.
    High,
    /// Critical — privileged, irreversible, or user-intent-sensitive.
    Critical,
}

/// Provenance tag carried by `ActionRequest` from L2.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ProvenanceTag {
    /// Public source.
    Public,
    /// Session-only ephemeral.
    Session,
    /// Durable persona-scoped memory.
    Durable,
    /// Private memory (strict posture gate).
    Private,
    /// Untrusted input (default when tags missing).
    UntrustedInput,
    /// Web-scraped content.
    ScrapedContent,
    /// Extracted user preference (lower confidence).
    ExtractedPreference,
}
