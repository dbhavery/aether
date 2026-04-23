import { describe, expect, it } from "vitest";

import {
  isSpeechProvider,
  speechProviderShortLabel,
  speechRouteSummary,
  SPEECH_PROVIDER_IDS,
  SPEECH_PROVIDER_REGISTRY,
} from "./speechProviders";

describe("SPEECH_PROVIDER_REGISTRY", () => {
  it("includes every shipping speech provider id", () => {
    expect(SPEECH_PROVIDER_IDS.has("whispercpp-speech")).toBe(true);
    expect(SPEECH_PROVIDER_IDS.size).toBe(1);
  });

  it("exposes a shortLabel for each row", () => {
    for (const entry of SPEECH_PROVIDER_REGISTRY) {
      expect(entry.shortLabel.trim().length).toBeGreaterThan(0);
    }
  });
});

describe("isSpeechProvider", () => {
  it("recognises whispercpp-speech", () => {
    expect(isSpeechProvider("whispercpp-speech")).toBe(true);
  });

  it.each(["ollama", "ollama-vision", "reflex-stub", "", "unknown"])(
    "%s is NOT a speech provider",
    (id) => {
      expect(isSpeechProvider(id)).toBe(false);
    },
  );

  it("treats null and undefined as not a speech provider", () => {
    expect(isSpeechProvider(null)).toBe(false);
    expect(isSpeechProvider(undefined)).toBe(false);
  });
});

describe("speechProviderShortLabel", () => {
  it("maps known speech provider ids to friendly labels", () => {
    expect(speechProviderShortLabel("whispercpp-speech")).toBe("whisper.cpp");
  });

  it("returns null for non-speech providers and missing values", () => {
    expect(speechProviderShortLabel("ollama")).toBeNull();
    expect(speechProviderShortLabel("ollama-vision")).toBeNull();
    expect(speechProviderShortLabel(null)).toBeNull();
    expect(speechProviderShortLabel(undefined)).toBeNull();
    expect(speechProviderShortLabel("")).toBeNull();
  });
});

describe("speechRouteSummary", () => {
  it("combines provider + model when both are known", () => {
    expect(speechRouteSummary("whispercpp-speech", "ggml-base.en.bin")).toBe(
      "whisper.cpp · ggml-base.en.bin",
    );
  });

  it("falls back to the provider label when the model is missing", () => {
    expect(speechRouteSummary("whispercpp-speech", null)).toBe("whisper.cpp");
    expect(speechRouteSummary("whispercpp-speech", undefined)).toBe(
      "whisper.cpp",
    );
    expect(speechRouteSummary("whispercpp-speech", "")).toBe("whisper.cpp");
    expect(speechRouteSummary("whispercpp-speech", "   ")).toBe("whisper.cpp");
  });

  it("returns null when the provider is not a known speech route", () => {
    expect(speechRouteSummary("ollama-vision", "llava")).toBeNull();
    expect(speechRouteSummary("reflex-stub", null)).toBeNull();
    expect(speechRouteSummary(null, null)).toBeNull();
    expect(speechRouteSummary(undefined, "whisper")).toBeNull();
  });
});
