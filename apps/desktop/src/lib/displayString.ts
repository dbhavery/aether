// Tiny pure helpers for compacting strings in cramped UI surfaces
// (e.g. the Trust drawer body line, where a long model id like
// "qwen2.5-vl-72b-instruct-q4_k_m" can otherwise dominate the row).
//
// Pure data in, pure data out — no React, no Tauri imports — so these
// can be reused anywhere and tested without DOM scaffolding.

/**
 * Truncate a string for tight inline display, keeping the prefix and
 * appending an ellipsis when the value exceeds `max`. The full string
 * is intended to be preserved separately (e.g. via a `title` attribute
 * or tooltip) so the original is still recoverable on hover.
 *
 * Behavior:
 *   - returns the original `s` when `s.length <= max`,
 *   - returns the first `max - 1` characters followed by `…` when
 *     longer (so the result length is exactly `max`).
 *
 * `max` must be at least 1; values below that are clamped up so we
 * never return an empty string from a non-empty input.
 */
export function truncateForDisplay(s: string, max: number): string {
  const limit = Math.max(1, Math.floor(max));
  if (s.length <= limit) return s;
  return s.slice(0, limit - 1) + "…";
}

/**
 * Middle-truncate a string so both ends survive — better for
 * filename-style identifiers where the suffix carries information
 * (e.g. quantization tags like `q4_k_m` on a model id).
 *
 * Behavior:
 *   - returns the original `s` when `s.length <= max`,
 *   - otherwise returns `<prefix>…<suffix>` where `suffix` is the
 *     last `suffixLen` characters and `prefix` fills the rest, so
 *     the result length is exactly `max`.
 *
 * `max` is clamped to ≥ `suffixLen + 2` so the prefix always gets
 * at least one character and we never collapse to `…<suffix>`.
 * `suffixLen` defaults to 8 — long enough to preserve a typical
 * quantization tag (`q4_k_m` = 6 chars + a leading `-`), short
 * enough to leave the prefix room to breathe at small widths.
 */
export function truncateMiddleForDisplay(
  s: string,
  max: number,
  suffixLen = 8,
): string {
  const suf = Math.max(1, Math.floor(suffixLen));
  const limit = Math.max(suf + 2, Math.floor(max));
  if (s.length <= limit) return s;
  const tail = s.slice(s.length - suf);
  const head = s.slice(0, limit - 1 - suf);
  return head + "…" + tail;
}
