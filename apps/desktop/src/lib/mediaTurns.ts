// Centralised classification of telemetry `kind` strings produced by
// the camera / screen `analyze_frame` path.
//
// Mirrors the four string constants the Rust `analyze_frame` command
// emits in apps/desktop/src-tauri/src/commands.rs:
//   - frame_analyzed     — model returned a response
//   - frame_blocked      — policy blocked the turn after permission
//   - permission_denied  — media permission set to Deny
//   - permission_ask     — media permission still on Ask; UI must
//                          flip to Allow before retrying
//
// Extracted here (out of TrustDrawer.tsx) so the contract has a
// single home and is unit-testable without dragging React in.

export const MEDIA_TURN_KINDS: ReadonlySet<string> = new Set([
  "frame_analyzed",
  "frame_blocked",
  "permission_denied",
  "permission_ask",
]);

/** True when this telemetry entry came from a camera/screen frame turn. */
export function isMediaTurn(kind: string): boolean {
  return MEDIA_TURN_KINDS.has(kind);
}
