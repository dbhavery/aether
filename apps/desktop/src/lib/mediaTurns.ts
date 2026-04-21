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

/**
 * Stable ids of every VisionProvider implementation registered in
 * the shell. Mirrors the Rust id() returns for OllamaVisionProvider
 * (`"ollama-vision"`) and LlamaCppVisionProvider (`"llamacpp-vision"`).
 * Used by the Trust drawer's History tab to badge media turns
 * served by a vision-capable provider.
 */
export const VISION_PROVIDER_IDS: ReadonlySet<string> = new Set([
  "ollama-vision",
  "llamacpp-vision",
]);

/** True when the telemetry `provider` string names a known vision provider. */
export function isVisionProvider(provider: string | null | undefined): boolean {
  if (!provider) return false;
  return VISION_PROVIDER_IDS.has(provider);
}

/**
 * Short display label for the vision-provider badge in the Trust
 * drawer. `null` when the provider is not a known vision route.
 */
export function visionProviderShortLabel(
  provider: string | null | undefined,
): string | null {
  if (!provider) return null;
  switch (provider) {
    case "ollama-vision":
      return "Ollama vision";
    case "llamacpp-vision":
      return "llama.cpp vision";
    default:
      return null;
  }
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
