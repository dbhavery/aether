//! # aether-l2-memory
//!
//! L2 owns the companion memory kernel: the six memory domains and
//! the session-memory store used by the runtime for short-range
//! conversational continuity.
//!
//! ADR-0001 (2026-04-23) retired the pre-V2 kernel stub
//! (`MemoryKernel`, `MemoryItem`, `PrivacyClass`, `RetentionKind`,
//! `EmbeddingStore`, `EmbeddingRef`, and the old six-variant
//! Personal/Work/... `MemoryDomain`). The six-domain V2 taxonomy
//! (Session / Durable / Facts / Projects / Preferences / Artifacts)
//! is now hosted here in `domain.rs` and `SessionMemoryStore` is the
//! shared storage contract.
//!
//! Source: `docs/MEMORY-V2-ARCHITECTURE.md`,
//! `docs/adr/ADR-0001-memory-domain-reconciliation.md`.

#![deny(unsafe_code)]
#![warn(missing_docs)]

pub mod domain;
pub mod error;
pub mod session;

#[cfg(feature = "sqlite-backend")]
pub mod sqlite_session;

pub use domain::MemoryDomain;
pub use error::L2Error;
pub use session::{
    render_transcript, InMemorySessionMemoryStore, MemoryRole, RecentMemoryConfig,
    RecentMemoryWindow, SessionMemoryStore, TurnMemoryRecord,
};

#[cfg(feature = "sqlite-backend")]
pub use sqlite_session::{DurableSessionStore, RetentionPolicy, SqliteSessionMemoryStore};
