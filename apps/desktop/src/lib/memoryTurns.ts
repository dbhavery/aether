// Centralised classification of telemetry `kind` strings produced by
// the Memory V2 shell service (`apps/desktop/src-tauri/src/memory_service.rs`).
//
// Mirrors the six string constants the Rust service emits via the
// `telemetry_kind` module. If a new memory kind lands server-side,
// both this allow-list AND the matching test must be updated in the
// same PR — the test pins the set size so a silent drift fails CI.
//
//   - memory_written       — item persisted (auto-path or
//                            post-approval path).
//   - memory_write_asked   — user-sensitive write required approval
//                            and got it (fires alongside memory_written).
//   - memory_write_denied  — write refused by `MemoryRisk::Deny` OR
//                            rejected by L5 posture (Observer, degraded).
//   - memory_forgotten     — user or retention sweep evicted an item.
//   - memory_edited        — user edited an existing item in place.
//   - memory_retrieval     — sampled read audit; fires every ~100
//                            reads per domain per session (design §4).
//
// Split from `voiceTurns.ts` / `mediaTurns.ts` so the memory surface
// has a single home — modalities have independent audit and
// retention concerns and will diverge further as the Memory tab
// (step 4) and retention sweep (step 5) land.

export const MEMORY_TURN_KINDS: ReadonlySet<string> = new Set([
  "memory_written",
  "memory_write_asked",
  "memory_write_denied",
  "memory_forgotten",
  "memory_edited",
  "memory_retrieval",
]);

/** True when this telemetry entry came from the Memory V2 service. */
export function isMemoryTurn(kind: string): boolean {
  return MEMORY_TURN_KINDS.has(kind);
}
