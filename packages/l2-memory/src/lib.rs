//! # aether-l2-memory
//!
//! **Status:** Wave 4 stub.
//!
//! L2 owns the companion memory kernel: the 6 memory domains, memory-item
//! storage, embedding references, and provenance tags consumed by L5.
//! Source: `planning/plans/L2_memory_kernel_system_design.md`,
//! `planning/plans/implementation_prep/L2_interface_pack.md`,
//! `planning/plans/implementation_prep/sqlite_schema_pack.md` §3e.

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod error;
pub mod kernel;

pub use error::L2Error;
pub use kernel::{
    EmbeddingRef, EmbeddingStore, MemoryDomain, MemoryId, MemoryItem, MemoryKernel, PrivacyClass,
    ProvenanceTag, RetentionKind,
};
