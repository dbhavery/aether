//! # aether-telemetry
//!
//! Telemetry surface. **Wave 1 placeholder — local-only default.**
//!
//! Doctrine: no cloud telemetry is ever enabled without explicit user opt-in
//! through an L5 policy grant. Default sinks are local `tracing` subscribers
//! only. See `SECURITY.md` and `ARCHITECTURE.md` (the L5 policy gate).

#![deny(unsafe_code)]
#![warn(missing_docs)]

use serde::{Deserialize, Serialize};

/// Telemetry sink mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum SinkMode {
    /// Default — local rolling log file only.
    #[default]
    LocalOnly,
    /// Local + OTLP export (requires an L5 grant with `telemetry_export` capability).
    LocalAndOtlp,
    /// Telemetry disabled entirely.
    Off,
}

/// Telemetry-layer error.
#[derive(Debug, thiserror::Error)]
pub enum TelemetryError {
    /// Export attempted without the required L5 grant.
    #[error("otlp export attempted without an active grant")]
    MissingGrant,
    /// Placeholder for unimplemented surface.
    #[error("not yet implemented — Wave 3+")]
    NotImplemented,
}

// TODO(wave-3): `init_tracing(SinkMode)` that wires a local rolling file
// subscriber + optional OTLP exporter behind a cargo feature.
// TODO(wave-3): a thin `Metric` / `Event` structured-log API used by every
// layer crate, keyed on `source_layer` and `change_id` from event-bus.

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_sink_is_local_only() {
        let m: SinkMode = Default::default();
        assert_eq!(m, SinkMode::LocalOnly);
    }
}
