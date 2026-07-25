# @aether/telemetry

**Status:** Wave 1 placeholder — local-only default.

Telemetry wrapper. Local-only by default; OTLP export is an opt-in capability gated by an L5 policy grant.

## References

- `SECURITY.md` — trust/security posture (export is opt-in).
- `ARCHITECTURE.md` — the L5 policy gate and autonomy/risk-class framework.

## Wave 1 contents

- `SinkMode { LocalOnly (default), LocalAndOtlp, Off }`.
- `TelemetryError`.

## Next wave

Wave 3 wires a real `tracing` subscriber + optional OTLP exporter gated by `SinkMode` and an active L5 grant.
