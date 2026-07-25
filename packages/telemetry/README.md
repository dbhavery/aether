# @aether/telemetry

**Status:** Wave 1 placeholder — local-only default.

Telemetry wrapper. Local-only by default; OTLP export is an opt-in capability gated by an L5 policy grant.

## References

- `ARCHITECTURE.md` — telemetry posture and the L5-gated export capability.
- `SECURITY.md` — the trust and reporting model.

## Wave 1 contents

- `SinkMode { LocalOnly (default), LocalAndOtlp, Off }`.
- `TelemetryError`.

## Next wave

Wave 3 wires a real `tracing` subscriber + optional OTLP exporter gated by `SinkMode` and an active L5 grant.
