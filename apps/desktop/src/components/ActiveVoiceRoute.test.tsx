import { describe, expect, it } from "vitest";

import { formatVoiceRouteHint, speechRouteLabel } from "./ActiveVoiceRoute";
import type { VoiceStatus } from "../lib/types";

function status(opts: Partial<VoiceStatus> = {}): VoiceStatus {
  return {
    enabled: false,
    active_id: null,
    label: null,
    active_model: null,
    providers: [],
    ...opts,
  };
}

describe("formatVoiceRouteHint", () => {
  it("reports the disabled state loudly when no provider is active", () => {
    expect(formatVoiceRouteHint(status())).toBe(
      "Voice disabled — configure a speech provider",
    );
  });

  it("combines provider + model when both are present", () => {
    expect(
      formatVoiceRouteHint(
        status({
          enabled: true,
          active_id: "whispercpp-speech",
          label: "whisper.cpp · ggml-base.en",
          active_model: "ggml-base.en",
        }),
      ),
    ).toBe("whisper.cpp · ggml-base.en");
  });

  it("falls back to provider label when no model id is known", () => {
    expect(
      formatVoiceRouteHint(
        status({
          enabled: true,
          active_id: "whispercpp-speech",
          label: "whisper.cpp",
          active_model: null,
        }),
      ),
    ).toBe("whisper.cpp");
  });

  it("uses the long label for an unknown provider id", () => {
    expect(
      formatVoiceRouteHint(
        status({
          enabled: true,
          active_id: "future-stt",
          label: "future STT · v0",
          active_model: null,
        }),
      ),
    ).toBe("future STT · v0");
  });
});

describe("speechRouteLabel", () => {
  it("maps known ids to registry shortLabels", () => {
    expect(speechRouteLabel("whispercpp-speech", "whatever")).toBe(
      "whisper.cpp",
    );
  });

  it("falls back to the long label when the id is unknown", () => {
    expect(speechRouteLabel("future-stt", "Future STT · v0")).toBe(
      "Future STT · v0",
    );
  });

  it("falls back to the id when even the long label is missing", () => {
    expect(speechRouteLabel("future-stt", null)).toBe("future-stt");
  });

  it("falls back to a generic 'Voice' when everything is null", () => {
    expect(speechRouteLabel(null, null)).toBe("Voice");
  });
});
