//! # aether-l2-memory
//!
//! **Status:** Wave 4 stub.
//!
//! L2 owns the companion memory kernel: the 6 memory domains, memory-item
//! storage, embedding references, and provenance tags consumed by L5.
//! Source: `ARCHITECTURE.md`.

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
