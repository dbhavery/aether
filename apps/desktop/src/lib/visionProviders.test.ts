import { describe, expect, it } from "vitest";

import {
  isVisionProvider,
  visionProviderShortLabel,
  VISION_PROVIDER_IDS,
  VISION_PROVIDER_REGISTRY,
} from "./visionProviders";

describe("VISION_PROVIDER_REGISTRY", () => {
  it("includes both built-in vision adapters", () => {
    const ids = VISION_PROVIDER_REGISTRY.map((p) => p.id).sort();
    expect(ids).toEqual(["llamacpp-vision", "ollama-vision"]);
  });

  it("ships a short label for every entry", () => {
    for (const entry of VISION_PROVIDER_REGISTRY) {
      expect(entry.shortLabel.length).toBeGreaterThan(0);
    }
  });

  it("derives VISION_PROVIDER_IDS from the registry", () => {
    expect(VISION_PROVIDER_IDS.size).toBe(VISION_PROVIDER_REGISTRY.length);
    for (const entry of VISION_PROVIDER_REGISTRY) {
      expect(VISION_PROVIDER_IDS.has(entry.id)).toBe(true);
    }
  });
});

describe("isVisionProvider", () => {
  it("returns true for known ids", () => {
    expect(isVisionProvider("ollama-vision")).toBe(true);
    expect(isVisionProvider("llamacpp-vision")).toBe(true);
  });

  it("returns false for non-vision providers and missing values", () => {
    expect(isVisionProvider("ollama")).toBe(false);
    expect(isVisionProvider("reflex-stub")).toBe(false);
    expect(isVisionProvider(null)).toBe(false);
    expect(isVisionProvider(undefined)).toBe(false);
    expect(isVisionProvider("")).toBe(false);
  });
});

describe("visionProviderShortLabel", () => {
  it("returns the short label for known ids", () => {
    expect(visionProviderShortLabel("ollama-vision")).toBe("Ollama vision");
    expect(visionProviderShortLabel("llamacpp-vision")).toBe(
      "llama.cpp vision",
    );
  });

  it("returns null for unknown / missing ids", () => {
    expect(visionProviderShortLabel("ollama")).toBeNull();
    expect(visionProviderShortLabel("future-provider")).toBeNull();
    expect(visionProviderShortLabel(null)).toBeNull();
    expect(visionProviderShortLabel(undefined)).toBeNull();
    expect(visionProviderShortLabel("")).toBeNull();
  });
});
