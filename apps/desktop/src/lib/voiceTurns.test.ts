import { describe, expect, it } from "vitest";

import { isVoiceTurn, VOICE_TURN_KINDS } from "./voiceTurns";

describe("VOICE_TURN_KINDS", () => {
  it("includes every kind the transcribe_utterance Rust command emits", () => {
    // Mirrors apps/desktop/src-tauri/src/commands.rs::transcribe_utterance
    // outcome + telemetry strings. If a new voice kind lands
    // server-side, this contract must be updated in lockstep.
    const expected = new Set([
      "utterance_transcribed",
      "utterance_blocked",
      "utterance_invalid",
      "mic_permission_denied",
      "mic_permission_ask",
    ]);
    expect(VOICE_TURN_KINDS.size).toBe(expected.size);
    for (const k of expected) {
      expect(VOICE_TURN_KINDS.has(k)).toBe(true);
    }
  });
});

describe("isVoiceTurn", () => {
  it.each([
    "utterance_transcribed",
    "utterance_blocked",
    "utterance_invalid",
    "mic_permission_denied",
    "mic_permission_ask",
  ])("classifies %s as a voice turn", (kind) => {
    expect(isVoiceTurn(kind)).toBe(true);
  });

  it.each([
    "completed",
    "denied",
    "needs_upgrade",
    "draft_only",
    "provider_error",
    // Media turns are explicitly NOT voice turns — the two allow-lists
    // must stay disjoint so the Trust drawer can filter either
    // modality independently.
    "frame_analyzed",
    "frame_blocked",
    "frame_invalid",
    "permission_denied",
    "permission_ask",
    "",
    "UTTERANCE_TRANSCRIBED",
    "utterance_transcribed_extra",
  ])("excludes non-voice kind %s", (kind) => {
    expect(isVoiceTurn(kind)).toBe(false);
  });
});
