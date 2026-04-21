import { describe, expect, it } from "vitest";

import { buildMetaParts } from "./Transcript";
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

  it("inserts the model chip after the provider for vision turns", () => {
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
      "Ollama vision · llava:latest · http://127.0.0.1:11434",
      "ollama-vision",
      "llava:latest",
      "1.5s",
      "p256/c12 tok",
    ]);
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

  it("falls back to a single token chip when only one count is present", () => {
    expect(
      buildMetaParts(meta({ provider: "ollama", completion_tokens: 7 })),
    ).toEqual(["ollama", "7 tok"]);
    expect(
      buildMetaParts(meta({ provider: "ollama", prompt_tokens: 19 })),
    ).toEqual(["ollama", "19 tok"]);
  });
});
