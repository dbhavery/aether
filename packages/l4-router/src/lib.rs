//! # aether-l4-router
//!
//! **Status:** Wave 4 stub.
//!
//! L4 owns the model + tool router: the 7-tier abstraction (reflex → frontier),
//! tool-call dispatch, per-request policy gating, cost-event emission,
//! Decision-4 per-step re-evaluation.
//! Source: `ARCHITECTURE.md`.

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod error;
pub mod router;

pub use error::L4Error;
pub use router::{
    ModelRouter, ProviderAdapter, ProviderId, RouterTier, ToolCall, ToolError, ToolResult,
};
