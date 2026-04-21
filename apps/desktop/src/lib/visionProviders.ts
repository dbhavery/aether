// Single source of truth for the TS-side vocabulary of vision
// provider ids and their short, user-facing labels.
//
// These ids must mirror each Rust `VisionProvider::id()` return:
//   - OllamaVisionProvider   → "ollama-vision"
//   - LlamaCppVisionProvider → "llamacpp-vision"
//
// Adding a new vision adapter on the Rust side requires one edit
// here (one row in the registry) and nothing else in the TS layer.
// Helpers in `mediaTurns.ts`, the badge in `ActiveVisionRoute.tsx`,
// and the Trust drawer's history badge all derive from this list.
//
// This module is intentionally pure data + tiny helpers. No React,
// no Tauri imports — keeps it cheap to consume from any layer and
// trivial to unit-test.

/** One row in the shared provider vocabulary. */
export interface VisionProviderEntry {
  /** Stable id — mirrors `VisionProvider::id()` on the Rust side. */
  readonly id: string;
  /** Plain-language label shown in compact UI surfaces (badge,
   * history pill, route hint). Long human labels (e.g. the full
   * `Ollama vision · model · base_url` line) come from the Rust
   * `label()` method and live in `VisionStatus.label` — not here. */
  readonly shortLabel: string;
}

/**
 * The canonical list of vision providers the desktop shell knows
 * about. Insertion order is irrelevant for lookups (helpers below
 * key by id) but is preserved for callers that want a stable
 * iteration order.
 */
export const VISION_PROVIDER_REGISTRY: ReadonlyArray<VisionProviderEntry> = [
  { id: "ollama-vision", shortLabel: "Ollama vision" },
  { id: "llamacpp-vision", shortLabel: "llama.cpp vision" },
];

/** Stable id set, derived from the registry. */
export const VISION_PROVIDER_IDS: ReadonlySet<string> = new Set(
  VISION_PROVIDER_REGISTRY.map((p) => p.id),
);

/** True when the given string names a known vision provider. */
export function isVisionProvider(
  provider: string | null | undefined,
): boolean {
  if (!provider) return false;
  return VISION_PROVIDER_IDS.has(provider);
}

/**
 * Plain-language label for the given vision provider id, or `null`
 * when the id is unknown. Callers that want a softer fallback
 * (e.g. "show the long label or the raw id when we don't recognise
 * the id") can compose: `shortLabelFor(id) ?? label ?? id ?? "Vision"`.
 */
export function visionProviderShortLabel(
  provider: string | null | undefined,
): string | null {
  if (!provider) return null;
  const entry = VISION_PROVIDER_REGISTRY.find((p) => p.id === provider);
  return entry ? entry.shortLabel : null;
}
