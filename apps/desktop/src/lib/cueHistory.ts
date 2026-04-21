// Per-panel recent-cue history.
//
// Stored in localStorage so the choice survives reloads but does not
// leak into the durable conversation memory (frame turns get their
// own user-role memory entry already; the cue list is UI sugar, not
// persisted dialogue).
//
// Each panel ("camera", "screen") gets its own bounded list. Newest
// entries are first. Re-pushing an existing cue moves it to the
// front — the user's intent ("repeat what I just asked") wins over
// chronological strictness.

export type CuePanel = "camera" | "screen";

export const MAX_CUE_HISTORY = 5;

const KEY_PREFIX = "aether.cue-history.";

function storageKey(panel: CuePanel): string {
  return `${KEY_PREFIX}${panel}`;
}

function safeReadStorage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Read recent cues for a panel, newest first. Capped at `MAX_CUE_HISTORY`. */
export function readCueHistory(panel: CuePanel): string[] {
  const ls = safeReadStorage();
  if (!ls) return [];
  try {
    const raw = ls.getItem(storageKey(panel));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((s): s is string => typeof s === "string" && s.trim() !== "")
      .slice(0, MAX_CUE_HISTORY);
  } catch {
    return [];
  }
}

/**
 * Pure projection of "current history + new cue → new history".
 * Exposed for unit tests; UI calls `pushCue` which wraps this.
 *
 * Rules:
 *   - empty / whitespace-only cues are ignored,
 *   - duplicates (case-sensitive, trimmed) are de-duplicated and the
 *     existing entry is moved to the front,
 *   - the list is capped at `MAX_CUE_HISTORY`.
 */
export function applyCue(history: string[], cue: string): string[] {
  const trimmed = cue.trim();
  if (trimmed === "") return history;
  const filtered = history.filter((c) => c !== trimmed);
  return [trimmed, ...filtered].slice(0, MAX_CUE_HISTORY);
}

/** Persist a new cue at the front of `panel`'s history. Returns the
 * new list so callers can update React state without re-reading. */
export function pushCue(panel: CuePanel, cue: string): string[] {
  const next = applyCue(readCueHistory(panel), cue);
  const ls = safeReadStorage();
  if (!ls) return next;
  try {
    ls.setItem(storageKey(panel), JSON.stringify(next));
  } catch {
    // Quota errors are non-fatal — the list still works in-memory
    // for the current session.
  }
  return next;
}

/** Wipe history for a panel. */
export function clearCueHistory(panel: CuePanel): void {
  const ls = safeReadStorage();
  if (!ls) return;
  try {
    ls.removeItem(storageKey(panel));
  } catch {
    // ignore
  }
}
