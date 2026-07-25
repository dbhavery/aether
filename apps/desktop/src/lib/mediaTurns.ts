// Centralised classification of telemetry `kind` strings produced by
// the camera / screen `analyze_frame` path.
//
// Mirrors the five string constants the Rust `analyze_frame` command
// emits in apps/desktop/src-tauri/src/commands.rs:
//   - frame_analyzed     — model returned a response
//   - frame_blocked      — policy blocked the turn after permission
//   - frame_invalid      — shell-side validate_frame_data_url rejected
//                          the payload (empty body, bad scheme, etc.)
//                          before any provider call ran
//   - permission_denied  — media permission set to Deny
//   - permission_ask     — media permission still on Ask; UI must
//                          flip to Allow before retrying
//
// Extracted here (out of TrustDrawer.tsx) so the contract has a
// single home and is unit-testable without dragging React in.
//
// Vision-provider id helpers live in `./visionProviders.ts` — the
// id ↔ short-label table has a single home so adding a third adapter
// is one edit, not four. We re-export here for back-compat with
// callers that already imported from this module.

export {
  isVisionProvider,
  VISION_PROVIDER_IDS,
  visionProviderShortLabel,
} from "./visionProviders";

import { visionProviderShortLabel } from "./visionProviders";

export const MEDIA_TURN_KINDS: ReadonlySet<string> = new Set([
  "frame_analyzed",
  "frame_blocked",
  "frame_invalid",
  "permission_denied",
  "permission_ask",
]);

/** True when this telemetry entry came from a camera/screen frame turn. */
export function isMediaTurn(kind: string): boolean {
  return MEDIA_TURN_KINDS.has(kind);
}

/**
 * Combined "<provider> · <model>" label for the Trust drawer's
 * History tab. Returns `null` when the provider isn't a known vision
 * route. When the provider is known but the model is missing, falls
 * back to the provider label alone — honest "we know it was a vision
 * route, we don't know which model" copy beats inventing a name.
 */
export function visionRouteSummary(
  provider: string | null | undefined,
  model: string | null | undefined,
): string | null {
  const providerLabel = visionProviderShortLabel(provider);
  if (!providerLabel) return null;
  const trimmed = typeof model === "string" ? model.trim() : "";
  return trimmed.length > 0 ? `${providerLabel} · ${trimmed}` : providerLabel;
}
