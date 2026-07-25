//! # aether-l6-persona
//!
//! **Status:** Wave 4 stub.
//!
//! L6 compiles persona packs into the six typed artifacts consumed by
//! L1/L3/L4/L5. Deterministic compilation, signature-verified privileged
//! overlays, hot-reload state machine.
//! Source: `ARCHITECTURE.md` and `docs/PERSONA-SCHEMA.md`.

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod compiler;
pub mod default_compiler;
pub mod error;
pub mod profile;

pub use compiler::{
    CompiledBehaviorMap, CompiledMemoryHints, CompiledPersona, CompiledPrompts,
    CompiledRoutingRules, CompiledToolAllowList, CompiledVoiceConfig, PersonaCompiler, PersonaId,
    PersonaPack, SwapState,
};
pub use default_compiler::DefaultPersonaCompiler;
pub use error::L6Error;
pub use profile::{Humor, PersonaProfile, Stance, Tone, Verbosity};
