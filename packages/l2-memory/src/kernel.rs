//! `MemoryKernel` + `EmbeddingStore` traits, `MemoryItem`, 6 domains.

use serde::{Deserialize, Serialize};

use crate::error::L2Error;

/// Stable id of a memory item.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct MemoryId(pub String);

/// External embedding handle (lives in an external vector store, not in
/// SQLite — see `ARCHITECTURE.md`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct EmbeddingRef(pub String);

/// Six memory domains per L2 interface pack §6.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MemoryDomain {
    /// Personal-life context (relationships, preferences, routines).
    Personal,
    /// Work / projects / tasks.
    Work,
    /// Health (always Strict posture).
    Health,
    /// Finance.
    Finance,
    /// Creative notes and drafts.
    Creative,
    /// System / operational memory about Aether itself.
    System,
}

/// Privacy class (mirrors the SQLite schema §3e `privacy_class`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PrivacyClass {
    /// Fine to share.
    Public,
    /// Default for memory not tagged otherwise.
    Private,
    /// Sensitive — never crosses remote routes without explicit waiver.
    Sensitive,
    /// Secret — encrypted-at-rest only; never in prompts.
    Secret,
}

/// Retention policy (mirrors the SQLite schema §3e `retention_kind`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RetentionKind {
    /// Dropped after the turn ends.
    Ephemeral,
    /// Dropped after the session ends.
    Session,
    /// Dropped after a fixed number of days.
    Days(u16),
    /// Kept indefinitely unless the user deletes.
    Permanent,
}

/// Provenance tag attached to every memory hit that enters a turn context.
/// Consumed by L5 for the privacy-posture gate.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ProvenanceTag {
    /// Came from public source.
    Public,
    /// Session-only ephemeral.
    Session,
    /// Durable persona-scoped memory.
    Durable,
    /// Private memory — strict posture gate.
    Private,
    /// Untrusted input (default when tags missing).
    UntrustedInput,
    /// Web-scraped content.
    ScrapedContent,
    /// Extracted preference (lower confidence).
    ExtractedPreference,
}

/// A single stored memory item. Content-addressed blobs live on the filesystem
/// (`content_ref`); short content is inlined (`content_inline`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryItem {
    /// Id.
    pub memory_id: MemoryId,
    /// Domain.
    pub domain: MemoryDomain,
    /// Short summary for ranking / UI.
    pub content_summary: String,
    /// Optional blob path (content-addressed).
    pub content_ref: Option<String>,
    /// Optional inline content (short values).
    pub content_inline: Option<String>,
    /// Optional external embedding handle.
    pub embedding_ref: Option<EmbeddingRef>,
    /// 0.0–1.0.
    pub confidence: f32,
    /// Privacy class (see enum).
    pub privacy_class: PrivacyClass,
    /// Retention policy.
    pub retention: RetentionKind,
    /// Whether the user may revoke.
    pub revocable: bool,
    /// Tombstoned flag.
    pub tombstoned: bool,
    /// Tags attached at ingest.
    pub provenance_tags: Vec<ProvenanceTag>,
}

/// External vector-store adapter. Concrete impl arrives in Wave 5+.
pub trait EmbeddingStore: Send + Sync {
    /// Upsert an embedding for `memory_id`; returns the store-scoped handle.
    fn upsert(&self, memory_id: &MemoryId, vector: &[f32]) -> Result<EmbeddingRef, L2Error>;

    /// Nearest neighbors of `vector` in the same domain.
    fn query(
        &self,
        domain: MemoryDomain,
        vector: &[f32],
        k: u32,
    ) -> Result<Vec<(MemoryId, f32)>, L2Error>;

    /// Delete an embedding handle.
    fn delete(&self, embedding_ref: &EmbeddingRef) -> Result<(), L2Error>;
}

/// Memory kernel surface. Every mutating call that crosses a user-visible
/// boundary is expected to be L5-gated by the caller.
pub trait MemoryKernel: Send + Sync {
    /// Store a new memory item.
    fn store(&self, item: MemoryItem) -> Result<MemoryId, L2Error>;

    /// Recall items matching a query string within a domain.
    fn recall(
        &self,
        domain: MemoryDomain,
        query: &str,
        limit: u32,
    ) -> Result<Vec<MemoryItem>, L2Error>;

    /// Tombstone an item (logical delete; retained for audit until GC).
    fn tombstone(&self, memory_id: &MemoryId) -> Result<(), L2Error>;

    /// Provenance tags currently assigned to a memory item.
    fn provenance(&self, memory_id: &MemoryId) -> Result<Vec<ProvenanceTag>, L2Error>;
}
