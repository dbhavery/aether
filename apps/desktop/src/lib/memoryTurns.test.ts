import { describe, expect, it } from "vitest";

import { isMemoryTurn, MEMORY_TURN_KINDS } from "./memoryTurns";

describe("MEMORY_TURN_KINDS", () => {
  it("includes every kind the Memory V2 Rust service emits", () => {
    // Mirrors apps/desktop/src-tauri/src/memory_service.rs::telemetry_kind.
    // If a new memory kind lands server-side, this contract must be
    // updated in lockstep — the assertion on `size` below catches
    // silent drift in either direction.
    const expected = new Set([
      "memory_written",
      "memory_write_asked",
      "memory_write_denied",
      "memory_forgotten",
      "memory_edited",
      "memory_retrieval",
    ]);
    expect(MEMORY_TURN_KINDS.size).toBe(expected.size);
    for (const k of expected) {
      expect(MEMORY_TURN_KINDS.has(k)).toBe(true);
    }
  });
});

describe("isMemoryTurn", () => {
  it.each([
    "memory_written",
    "memory_write_asked",
    "memory_write_denied",
    "memory_forgotten",
    "memory_edited",
    "memory_retrieval",
  ])("classifies %s as a memory turn", (kind) => {
    expect(isMemoryTurn(kind)).toBe(true);
  });

  it.each([
    // Regular turn-engine kinds must not be confused for memory.
    "completed",
    "denied",
    "needs_upgrade",
    "draft_only",
    "provider_error",
    // Media / voice kinds stay disjoint so the Trust drawer can
    // filter each modality independently.
    "frame_analyzed",
    "frame_blocked",
    "permission_denied",
    "permission_ask",
    "utterance_transcribed",
    "utterance_blocked",
    "mic_permission_denied",
    "mic_permission_ask",
    // Near-misses.
    "",
    "MEMORY_WRITTEN",
    "memory_written_extra",
    "memory_write",
  ])("excludes non-memory kind %s", (kind) => {
    expect(isMemoryTurn(kind)).toBe(false);
  });
});
