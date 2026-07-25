import { describe, expect, it } from "vitest";

import {
  isMediaTurn,
  isVisionProvider,
  MEDIA_TURN_KINDS,
  VISION_PROVIDER_IDS,
  visionProviderShortLabel,
  visionRouteSummary,
} from "./mediaTurns";

describe("MEDIA_TURN_KINDS", () => {
  it("includes every kind the analyze_frame Rust command emits", () => {
    // Mirrors apps/desktop/src-tauri/src/commands.rs::analyze_frame
    // outcome strings. If a new media kind lands server-side, this
    // contract must be updated in lockstep.
    const expected = new Set([
      "frame_analyzed",
      "frame_blocked",
      "frame_invalid",
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
    "frame_invalid",
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

describe("VISION_PROVIDER_IDS", () => {
  it("includes every shipping vision provider id", () => {
    expect(VISION_PROVIDER_IDS.has("ollama-vision")).toBe(true);
    expect(VISION_PROVIDER_IDS.has("llamacpp-vision")).toBe(true);
    expect(VISION_PROVIDER_IDS.size).toBe(2);
  });
});

describe("isVisionProvider", () => {
  it.each(["ollama-vision", "llamacpp-vision"])(
    "%s is a vision provider",
    (id) => {
      expect(isVisionProvider(id)).toBe(true);
    },
  );

  it.each(["ollama", "reflex-stub", "", "unknown"])(
    "%s is NOT a vision provider",
    (id) => {
      expect(isVisionProvider(id)).toBe(false);
    },
  );

  it("treats null and undefined as not a vision provider", () => {
    expect(isVisionProvider(null)).toBe(false);
    expect(isVisionProvider(undefined)).toBe(false);
  });
});

describe("visionProviderShortLabel", () => {
  it("maps known vision provider ids to friendly labels", () => {
    expect(visionProviderShortLabel("ollama-vision")).toBe("Ollama vision");
    expect(visionProviderShortLabel("llamacpp-vision")).toBe("llama.cpp vision");
  });

  it("returns null for non-vision providers and missing values", () => {
    expect(visionProviderShortLabel("ollama")).toBeNull();
    expect(visionProviderShortLabel("reflex-stub")).toBeNull();
    expect(visionProviderShortLabel(null)).toBeNull();
    expect(visionProviderShortLabel(undefined)).toBeNull();
    expect(visionProviderShortLabel("")).toBeNull();
  });
});

describe("visionRouteSummary", () => {
  it("combines provider + model when both are known", () => {
    expect(visionRouteSummary("ollama-vision", "llava:latest")).toBe(
      "Ollama vision · llava:latest",
    );
    expect(visionRouteSummary("llamacpp-vision", "minicpm-v")).toBe(
      "llama.cpp vision · minicpm-v",
    );
  });

  it("falls back to the provider label when the model is missing", () => {
    expect(visionRouteSummary("ollama-vision", null)).toBe("Ollama vision");
    expect(visionRouteSummary("ollama-vision", undefined)).toBe("Ollama vision");
    expect(visionRouteSummary("ollama-vision", "")).toBe("Ollama vision");
    // Whitespace-only model strings count as "missing".
    expect(visionRouteSummary("ollama-vision", "   ")).toBe("Ollama vision");
  });

  it("returns null when the provider is not a known vision route", () => {
    expect(visionRouteSummary("ollama", "llava")).toBeNull();
    expect(visionRouteSummary("reflex-stub", null)).toBeNull();
    expect(visionRouteSummary(null, null)).toBeNull();
    expect(visionRouteSummary(undefined, "llava")).toBeNull();
  });
});
