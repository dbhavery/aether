import { describe, expect, it } from "vitest";

import { formatRouteHint, providerShortLabel } from "./ActiveVisionRoute";
import type { VisionStatus } from "../lib/types";

function s(overrides: Partial<VisionStatus> = {}): VisionStatus {
  return {
    enabled: false,
    active_id: null,
    label: null,
    active_model: null,
    providers: [],
    ...overrides,
  };
}

describe("formatRouteHint", () => {
  it("returns text-only fallback when no provider is active", () => {
    expect(formatRouteHint(s())).toBe("Text-only fallback");
  });

  it("renders provider · model when a model is known", () => {
    const status = s({
      enabled: true,
      active_id: "ollama-vision",
      label: "Ollama vision · llava:latest · http://127.0.0.1:11434",
      active_model: "llava:latest",
    });
    expect(formatRouteHint(status)).toBe("Ollama vision · llava:latest");
  });

  it("falls back to provider only when no model id is reported", () => {
    const status = s({
      enabled: true,
      active_id: "llamacpp-vision",
      label: "llama.cpp vision · ? · http://127.0.0.1:8080",
      active_model: null,
    });
    expect(formatRouteHint(status)).toBe("llama.cpp vision");
  });

  it("uses the long label as a final fallback for unknown provider ids", () => {
    const status = s({
      enabled: true,
      active_id: "future-provider",
      label: "Cool future provider · v9000",
      active_model: "model-x",
    });
    expect(formatRouteHint(status)).toBe(
      "Cool future provider · v9000 · model-x",
    );
  });
});

describe("providerShortLabel", () => {
  it("maps the known provider ids to short labels", () => {
    expect(providerShortLabel("ollama-vision", null)).toBe("Ollama vision");
    expect(providerShortLabel("llamacpp-vision", null)).toBe("llama.cpp vision");
  });

  it("falls back to the long label when id is unknown", () => {
    expect(providerShortLabel("future", "Cool future · v1")).toBe(
      "Cool future · v1",
    );
  });

  it("falls back to the id when no label is available", () => {
    expect(providerShortLabel("future", null)).toBe("future");
  });

  it("returns 'Vision' as a last resort", () => {
    expect(providerShortLabel(null, null)).toBe("Vision");
  });
});
