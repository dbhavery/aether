import { describe, expect, it } from "vitest";

import { isMediaTurn, MEDIA_TURN_KINDS } from "./mediaTurns";

describe("MEDIA_TURN_KINDS", () => {
  it("includes every kind the analyze_frame Rust command emits", () => {
    // Mirrors apps/desktop/src-tauri/src/commands.rs::analyze_frame
    // outcome strings. If a new media kind lands server-side, this
    // contract must be updated in lockstep.
    const expected = new Set([
      "frame_analyzed",
      "frame_blocked",
      "permission_denied",
      "permission_ask",
    ]);
    expect(MEDIA_TURN_KINDS.size).toBe(expected.size);
    for (const k of expected) {
      expect(MEDIA_TURN_KINDS.has(k)).toBe(true);
    }
  });
});

describe("isMediaTurn", () => {
  it.each([
    "frame_analyzed",
    "frame_blocked",
    "permission_denied",
    "permission_ask",
  ])("classifies %s as a media turn", (kind) => {
    expect(isMediaTurn(kind)).toBe(true);
  });

  it.each([
    "completed",
    "denied",
    "needs_upgrade",
    "draft_only",
    "provider_error",
    "",
    "frame_analyzed_extra",
    "FRAME_ANALYZED",
  ])("excludes non-media kind %s", (kind) => {
    expect(isMediaTurn(kind)).toBe(false);
  });
});
