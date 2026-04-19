//! BYOK cost counters + re-arm surface (Decision 5 locked, 2026-04-18).
//!
//! Re-arm is **explicit and re-auth gated**; parked plans do not auto-resume.
//! UX flow: cap hit → `cost_threshold_hit` → L4 denies further for provider →
//! L1 repair/deflect → L7 modal with:
//!   - Raise cap      → `policy.set_cost_cap(...)`   (re-auth)
//!   - Reset counter  → `policy.reset_cost_counter`  (re-auth)
//!   - Switch to local tier → `router.set_tier_override(Local)`

use serde::{Deserialize, Serialize};

use crate::common::{Cents, MonotonicTimestamp, PersonaId, RequestId};

/// Opaque provider id (e.g. `"anthropic"`, `"openai"`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ProviderId(pub String);

/// Rolling window a counter / cap applies to.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CostWindow {
    /// Rolling 24h.
    Daily,
    /// Calendar month.
    Monthly,
    /// Single session.
    Session,
    /// A persona's monthly budget.
    PerPersona(PersonaId),
}

/// Threshold kinds emitted in `CostThresholdHit`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CostThreshold {
    /// Daily cap crossed.
    Daily,
    /// Monthly cap crossed.
    Monthly,
    /// Per-provider cap crossed.
    PerProvider,
    /// Per-persona cap crossed.
    PerPersona,
}

/// Configured cap.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostCap {
    /// Cap value in cents.
    pub cents: Cents,
    /// Early-warn percentage (0–100). `None` disables warn emission.
    pub warn_at_pct: Option<u8>,
}

/// Incoming cost event from L4 on every router completion.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostEvent {
    /// Provider that served the call.
    pub provider: ProviderId,
    /// Tokens in.
    pub tokens_in: u32,
    /// Tokens out.
    pub tokens_out: u32,
    /// Dollars charged (cents).
    pub dollars: Cents,
    /// Correlating request.
    pub request_id: RequestId,
    /// Monotonic timestamp.
    pub timestamp_mono: MonotonicTimestamp,
    /// Optional persona.
    pub persona_id: Option<PersonaId>,
    /// Optional session.
    pub session_id: Option<crate::common::SessionId>,
    /// True if the call failed (partial cost still counts).
    pub failed: bool,
}
