//! Common id and scalar newtypes used across L5 surfaces.
//!
//! These are placeholder newtypes. Real ULID / monotonic-clock implementations
//! land in Wave 3+. They exist now so every other module has stable shapes to
//! reference.

use serde::{Deserialize, Serialize};

macro_rules! id_newtype {
    ($name:ident, $doc:expr) => {
        #[doc = $doc]
        #[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
        pub struct $name(pub String);
    };
}

id_newtype!(RequestId, "ULID of a single `ActionRequest`. Process-unique.");
id_newtype!(TurnId, "L1 turn identifier; correlates with turn state machine.");
id_newtype!(TaskId, "Task id for task-scoped grants.");
id_newtype!(SessionId, "Session id for session-scoped counters and grants.");
id_newtype!(PersonaId, "Persona id. Privileged overlay flag is a separate field.");
id_newtype!(PresetId, "Named policy preset (Balanced, Operator, Analyst, ...).");
id_newtype!(ChangeId, "Correlation id for a write-class command chain.");
id_newtype!(AuditIdString, "String form of an audit id; see audit::AuditId.");

/// Bus-global monotonic sequence number.
pub type Seq = u64;

/// Integer cents (USD) — storage for cost math. No floats anywhere in grants.
pub type Cents = u64;

/// Monotonic nanoseconds since process start.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct MonotonicTimestamp(pub u64);

/// Wall-clock time — display and export only; never precedence.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct WallTimestamp {
    /// Seconds since UNIX epoch.
    pub epoch_s: i64,
    /// Nanosecond fraction.
    pub ns: u32,
}

/// Duration in nanoseconds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Duration(pub u64);

/// Reference to an actor in an audit row.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ActorRef {
    /// The current user (via L7).
    User,
    /// The runtime itself.
    System,
    /// A persona acting autonomously.
    Persona(PersonaId),
}

/// Capability-gated command token issued by L7 after re-auth.
///
/// Required for High / Critical capability IPC commands (revoke-all,
/// `set_preset`, cost-cap admin, etc.).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandToken {
    /// Opaque token bytes.
    pub token: String,
    /// Monotonic expiry.
    pub expires_at: MonotonicTimestamp,
}
