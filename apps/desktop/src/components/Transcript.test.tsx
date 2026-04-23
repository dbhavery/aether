import { describe, expect, it } from "vitest";

import {
  buildMetaParts,
  originChipForFooter,
  tierChipForFooter,
} from "./Transcript";
import type { MessageMeta } from "../lib/types";

function meta(overrides: Partial<MessageMeta> = {}): MessageMeta {
  return {
    tier: null,
    provider: null,
    ...overrides,
  };
}

describe("buildMetaParts", () => {
  it("returns an empty list when meta has no useful fields", () => {
    expect(buildMetaParts(meta())).toEqual([]);
  });

  it("renders text-only turns without a model chip", () => {
    const m = meta({
      tier: "local",
      provider: "ollama",
      latency_ms: 850,
      prompt_tokens: 12,
      completion_tokens: 34,
    });
    expect(buildMetaParts(m)).toEqual([
      "local",
      "ollama",
      "850ms",
      "p12/c34 tok",
    ]);
  });

  it("drops the duplicating tier chip on vision turns and shows provider · model instead", () => {
    const m = meta({
      tier: "Ollama vision · llava:latest · http://127.0.0.1:11434",
      provider: "ollama-vision",
      model: "llava:latest",
      latency_ms: 1500,
      prompt_tokens: 256,
      completion_tokens: 12,
    });
    const parts = buildMetaParts(m);
    expect(parts).toEqual([
      "ollama-vision",
      "llava:latest",
      "1.5s",
      "p256/c12 tok",
    ]);
  });

  it("drops tier on llama.cpp vision turns too", () => {
    const m = meta({
      tier: "llama.cpp vision · minicpm-v · http://127.0.0.1:8080",
      provider: "llamacpp-vision",
      model: "minicpm-v",
    });
    expect(buildMetaParts(m)).toEqual(["llamacpp-vision", "minicpm-v"]);
  });

  it("omits the model chip when model is empty / whitespace / undefined", () => {
    expect(buildMetaParts(meta({ provider: "ollama-vision", model: "" }))).toEqual([
      "ollama-vision",
    ]);
    expect(
      buildMetaParts(meta({ provider: "ollama-vision", model: "   " })),
    ).toEqual(["ollama-vision"]);
    expect(buildMetaParts(meta({ provider: "ollama-vision" }))).toEqual([
      "ollama-vision",
    ]);
  });

  it("keeps the tier chip on text-only turns where it adds info", () => {
    const m = meta({ tier: "local", provider: "ollama" });
    expect(buildMetaParts(m)).toEqual(["local", "ollama"]);
  });

  it("falls back to a single token chip when only one count is present", () => {
    expect(
      buildMetaParts(meta({ provider: "ollama", completion_tokens: 7 })),
    ).toEqual(["ollama", "7 tok"]);
    expect(
      buildMetaParts(meta({ provider: "ollama", prompt_tokens: 19 })),
    ).toEqual(["ollama", "19 tok"]);
  });
});

describe("originChipForFooter", () => {
  it("returns null when origin is absent", () => {
    expect(originChipForFooter(meta())).toBeNull();
  });

  it("labels voice turns", () => {
    expect(originChipForFooter(meta({ origin: "voice" }))).toBe("voice");
  });

  it("labels vision turns", () => {
    expect(originChipForFooter(meta({ origin: "vision" }))).toBe("vision");
  });
});

describe("buildMetaParts + origin chip", () => {
  it("prepends the voice chip on voice-originating turns", () => {
    const m = meta({
      origin: "voice",
      tier: "local",
      provider: "ollama",
      model: "ggml-base.en",
      latency_ms: 420,
    });
    const parts = buildMetaParts(m);
    expect(parts[0]).toBe("voice");
    expect(parts).toContain("ollama");
    expect(parts).toContain("ggml-base.en");
  });

  it("prepends the vision chip on vision-originating turns", () => {
    const m = meta({
      origin: "vision",
      tier: "Ollama vision · llava · http://127.0.0.1:11434",
      provider: "ollama-vision",
      model: "llava:latest",
    });
    const parts = buildMetaParts(m);
    expect(parts[0]).toBe("vision");
    // tier still dropped on vision turns
    expect(parts).not.toContain(
      "Ollama vision · llava · http://127.0.0.1:11434",
    );
    expect(parts).toContain("ollama-vision");
    expect(parts).toContain("llava:latest");
  });
});

describe("tierChipForFooter", () => {
  it("returns null when tier itself is missing", () => {
    expect(tierChipForFooter(meta())).toBeNull();
    expect(tierChipForFooter(meta({ tier: null }))).toBeNull();
  });

  it("preserves tier on text-only / non-vision providers", () => {
    expect(tierChipForFooter(meta({ tier: "local", provider: "ollama" })))
      .toBe("local");
    expect(
      tierChipForFooter(meta({ tier: "reflex-stub", provider: "reflex-stub" })),
    ).toBe("reflex-stub");
    // No provider at all → keep tier (we don't know it's a vision turn).
    expect(tierChipForFooter(meta({ tier: "local" }))).toBe("local");
  });

  it("drops tier on vision turns to avoid duplicating provider+model", () => {
    expect(
      tierChipForFooter(
        meta({
          tier: "Ollama vision · llava · http://127.0.0.1:11434",
          provider: "ollama-vision",
        }),
      ),
    ).toBeNull();
    expect(
      tierChipForFooter(
        meta({
          tier: "llama.cpp vision · minicpm · http://127.0.0.1:8080",
          provider: "llamacpp-vision",
        }),
      ),
    ).toBeNull();
  });
});
