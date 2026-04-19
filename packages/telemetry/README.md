# @aether/telemetry

**Status:** Wave 1 placeholder — local-only default.

Telemetry wrapper. Local-only by default; OTLP export is an opt-in capability gated by an L5 policy grant.

## References

- file:///C:/Users/dbhav/Projects/aether/planning/13_trust_security_redteam.md
- file:///C:/Users/dbhav/Projects/aether/planning/12_permissions_autonomy.md

## Wave 1 contents

- `SinkMode { LocalOnly (default), LocalAndOtlp, Off }`.
- `TelemetryError`.

## Next wave

Wave 3 wires a real `tracing` subscriber + optional OTLP exporter gated by `SinkMode` and an active L5 grant.
