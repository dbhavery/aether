//! Capability taxonomy and resource scopes.
//!
//! Source of truth: `ARCHITECTURE.md` (the L5 policy layer — the 7 capability
//! groups and 45+ sub-capabilities, the defaults table, and the locked decision
//! that adds `CostCapAdmin` + `AuditExport` to the canonical enum).
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

    // ----- Memory V2 coarse surface (step 1) -----
    // The four coarse capability variants `docs/MEMORY-V2-ARCHITECTURE.md`
    // §10 item 1 mandates. Added additively — the older, finer-grained
    // variants above remain valid for legacy consumers while the
    // Memory V2 policy surface wires the new ones into the capability
    // / audit path. Memory V2 step 2 defines their preset defaults
    // (per-domain Auto / Ask / Deny); for now they are additive-only
    // enum members with no preset policy entries, meaning any turn
    // that requests them returns `NeedsUpgrade` until step 2 lands —
    // exactly the behaviour we want for an L5-first slice.
    /// Memory V2: coarse "write any memory item" capability. Risk
    /// class is `Medium` by default; per-domain Ask semantics come
    /// from the `memory.json` policy surface in step 2.
    MemoryWrite,
    /// Memory V2: explicit per-item forget. Distinct from
    /// `MemoryDelete` (bulk). Retention-sweep eviction emits this
    /// so the audit log can distinguish user-initiated forgets from
    /// TTL expiry.
    MemoryForget,
    /// Memory V2: edit an existing memory item. Step 2 wires the
    /// `Ask` flow on user-sensitive domains.
    MemoryEdit,
    /// Memory V2: produce and persist an embedding vector for a
    /// memory item. Added by step 6 (ADR-0002); opt-in per
    /// `memory.json::embeddings.enabled`. Each embedding write
    /// produces one audit row via this capability. Not routed
    /// through the Ask flow — the embedding is a side effect of an
    /// already-allowed MemoryWrite, so the primary capability gates
    /// the user-visible decision.
    MemoryEmbed,
    /// Memory V2 / ADR-0005: retrieval-augmented read. Distinct
    /// from `MemoryRead` so future audit surfaces can filter
    /// retrieval-augmented reads from plain session recall. Emitted
    /// once per turn when the turn engine consults
    /// `EmbeddingStore::query_nearest`. Default posture Auto
    /// (parallel to `MemoryRead`); no Ask flow. Naming is
    /// extendable — future retrieval modes (web, code, graph) land
    /// as sibling variants rather than reopening this one.
    RetrievalContext,

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

    // ----- Persona delivery (ADR-0012, 2026-04-28 night) -----
    // Tier-2 persona pack lifecycle. Each variant emits one L5 audit
    // row when the desktop shell drives the corresponding L6
    // primitive. Default risks: Medium for install/uninstall (user
    // data dir mutation), Low for switch (pointer-only), Medium for
    // download (network egress on verified content). Default modes
    // are baked into the wave3_default policy so the wizard can run
    // its confirmation step without a redundant L5 modal on top.
    /// Fetch a Tier-2 persona pack zip from the manifest URL.
    /// Network egress; the SHA-256 + Ed25519 verification gates
    /// trust, not this capability.
    PersonaDownload,
    /// Extract a verified persona pack into the user's data dir.
    /// User data mutation; the wizard's confirmation step is the
    /// user-visible gate.
    PersonaInstall,
    /// Remove an installed persona pack. Default `Ask` when called
    /// outside a switch flow — explicit destruction warrants the
    /// modal.
    PersonaUninstall,
    /// Change which persona is currently active. Pointer-only;
    /// uninstall+install are emitted separately when a switch
    /// triggers them (ADR-0012 §Switch flow).
    PersonaSwitch,
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
