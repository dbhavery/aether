//! Memory V2 six-domain taxonomy.
//!
//! The canonical `MemoryDomain` enum — the single source of truth
//! across Companion for which domain owns a memory row. Previously this
//! enum lived in `apps/desktop/src-tauri/src/memory_config.rs`
//! alongside `MemoryConfig`; ADR-0001 (2026-04-23) relocated it here
//! so background jobs (retention sweep, embeddings worker) can speak
//! the taxonomy without coupling to the desktop binary.
//!
//! Tied to `docs/MEMORY-V2-ARCHITECTURE.md` §1 — the six domains are
//! frozen; adding a seventh is an architecture-level decision.
//! `MemoryRisk` (per-domain Auto/Ask/Deny policy) stays in the shell
//! because it is policy configuration, not the taxonomy itself.

use serde::{Deserialize, Serialize};

/// Memory domains as frozen by `docs/MEMORY-V2-ARCHITECTURE.md` §1.
/// Six, stable, additive-only for future builds. Serde wire format is
/// the lowercase id so persisted JSON reads naturally.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MemoryDomain {
    /// Turn-by-turn conversation within one session.
    Session,
    /// Recent conversation across sessions (rolling window, 30-day
    /// default).
    Durable,
    /// Explicit user-provided facts — user-sensitive.
    Facts,
    /// Named project scopes + associated notes / references.
    Projects,
    /// Per-user tuning (timezone, style, interaction defaults).
    Preferences,
    /// References to files, URLs, code snippets the user pinned —
    /// user-sensitive.
    Artifacts,
}

impl MemoryDomain {
    /// Every domain, in stable order. Used by the Settings UI to
    /// render rows and by tests to lock the set.
    pub const ALL: [MemoryDomain; 6] = [
        MemoryDomain::Session,
        MemoryDomain::Durable,
        MemoryDomain::Facts,
        MemoryDomain::Projects,
        MemoryDomain::Preferences,
        MemoryDomain::Artifacts,
    ];

    /// Lowercase wire / UI label.
    pub fn label(self) -> &'static str {
        match self {
            MemoryDomain::Session => "session",
            MemoryDomain::Durable => "durable",
            MemoryDomain::Facts => "facts",
            MemoryDomain::Projects => "projects",
            MemoryDomain::Preferences => "preferences",
            MemoryDomain::Artifacts => "artifacts",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_domains_enumerated() {
        assert_eq!(MemoryDomain::ALL.len(), 6);
    }

    #[test]
    fn labels_are_stable() {
        assert_eq!(MemoryDomain::Session.label(), "session");
        assert_eq!(MemoryDomain::Durable.label(), "durable");
        assert_eq!(MemoryDomain::Facts.label(), "facts");
        assert_eq!(MemoryDomain::Projects.label(), "projects");
        assert_eq!(MemoryDomain::Preferences.label(), "preferences");
        assert_eq!(MemoryDomain::Artifacts.label(), "artifacts");
    }
}
