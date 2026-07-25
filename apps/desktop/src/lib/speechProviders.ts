// Single source of truth for the TS-side vocabulary of speech
// (STT) provider ids and their short, user-facing labels. Mirrors
// `visionProviders.ts`.
//
// These ids must match each Rust `SpeechProvider::id()` return:
//   - WhisperCppSpeechProvider → "whispercpp-speech"
//
// Adding a new speech adapter on the Rust side requires one edit
// here (one row in the registry) and nothing else in the TS layer.
// Helpers in `VoiceBadge`, `ActiveVoiceRoute`, and Trust-drawer
// voice-route summaries all derive from this list.
//
// This module is intentionally pure data + tiny helpers. No React,
// no Tauri imports — cheap to consume from any layer and trivial to
// unit-test.

/** One row in the shared provider vocabulary. */
export interface SpeechProviderEntry {
  /** Stable id — mirrors `SpeechProvider::id()` on the Rust side. */
  readonly id: string;
  /** Plain-language label shown in compact UI surfaces. */
  readonly shortLabel: string;
}

/**
 * The canonical list of speech providers the desktop shell knows
 * about. Insertion order is irrelevant for lookups but is preserved
 * for callers that want a stable iteration order.
 */
export const SPEECH_PROVIDER_REGISTRY: ReadonlyArray<SpeechProviderEntry> = [
  { id: "whispercpp-speech", shortLabel: "whisper.cpp" },
];

/** Stable id set, derived from the registry. */
export const SPEECH_PROVIDER_IDS: ReadonlySet<string> = new Set(
  SPEECH_PROVIDER_REGISTRY.map((p) => p.id),
);

/** True when the given string names a known speech provider. */
export function isSpeechProvider(
  provider: string | null | undefined,
): boolean {
  if (!provider) return false;
  return SPEECH_PROVIDER_IDS.has(provider);
}

/**
 * Plain-language label for the given speech provider id, or `null`
 * when the id is unknown. Callers that want a softer fallback can
 * compose:
 *   `speechProviderShortLabel(id) ?? label ?? id ?? "Voice"`.
 */
export function speechProviderShortLabel(
  provider: string | null | undefined,
): string | null {
  if (!provider) return null;
  const entry = SPEECH_PROVIDER_REGISTRY.find((p) => p.id === provider);
  return entry ? entry.shortLabel : null;
}

/**
 * Combined "<provider> · <model>" label for the Trust drawer's
 * History tab — the voice analogue of `visionRouteSummary`. Returns
 * `null` when the provider isn't a known speech route. When the
 * provider is known but the model is missing, falls back to the
 * provider label alone — honest "we know it was a voice route, we
 * don't know which model" copy beats inventing a name.
 */
export function speechRouteSummary(
  provider: string | null | undefined,
  model: string | null | undefined,
): string | null {
  const providerLabel = speechProviderShortLabel(provider);
  if (!providerLabel) return null;
  const trimmed = typeof model === "string" ? model.trim() : "";
  return trimmed.length > 0 ? `${providerLabel} · ${trimmed}` : providerLabel;
}
