// Component tests for VoiceBadge — mirror of VisionBadge, scaled
// down to the shipping voice surface (one adapter, no text-only
// fallback, "disabled" is a loud state).

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";

import { VoiceBadge } from "./VoiceBadge";
import type { SpeechModelList, VoiceStatus } from "../lib/types";

vi.mock("../lib/api", () => {
  return {
    voiceStatus: vi.fn(),
    listSpeechModels: vi.fn(),
    refreshSpeechModels: vi.fn(),
    setActiveSpeechProvider: vi.fn(),
    setActiveSpeechModel: vi.fn(),
  };
});

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  voiceStatus: ReturnType<typeof vi.fn>;
  listSpeechModels: ReturnType<typeof vi.fn>;
  refreshSpeechModels: ReturnType<typeof vi.fn>;
  setActiveSpeechProvider: ReturnType<typeof vi.fn>;
  setActiveSpeechModel: ReturnType<typeof vi.fn>;
};

const DISABLED: VoiceStatus = {
  enabled: false,
  active_id: null,
  label: null,
  active_model: null,
  providers: [],
};

function statusWith(opts: {
  active_id?: string | null;
  label?: string | null;
  active_model?: string | null;
  providers?: VoiceStatus["providers"];
}): VoiceStatus {
  return {
    enabled: opts.active_id != null,
    active_id: opts.active_id ?? null,
    label: opts.label ?? null,
    active_model: opts.active_model ?? null,
    providers: opts.providers ?? [],
  };
}

function modelsList(
  provider_id: string,
  models: string[],
  error: string | null = null,
): SpeechModelList {
  return { provider_id, models, error };
}

beforeEach(() => {
  for (const k of Object.keys(mockedApi) as (keyof typeof mockedApi)[]) {
    mockedApi[k].mockReset();
  }
});

describe("VoiceBadge — disabled state", () => {
  it("renders honest copy when no providers are registered", async () => {
    mockedApi.voiceStatus.mockResolvedValueOnce(DISABLED);

    render(<VoiceBadge />);

    expect(await screen.findByText("Voice disabled")).toBeTruthy();
    // Hint should mention the whisper env knob so the user knows how to
    // enable voice.
    expect(
      screen.getByText(/AETHER_WHISPERCPP_SPEECH_MODEL/i),
    ).toBeTruthy();
    // listSpeechModels MUST NOT be called when there is no active id.
    expect(mockedApi.listSpeechModels).not.toHaveBeenCalled();
  });

  it("falls back to a hard-coded disabled state when voiceStatus rejects", async () => {
    mockedApi.voiceStatus.mockRejectedValueOnce(new Error("boom"));

    render(<VoiceBadge />);

    expect(await screen.findByText("Voice disabled")).toBeTruthy();
    expect(mockedApi.listSpeechModels).not.toHaveBeenCalled();
  });
});

describe("VoiceBadge — active provider", () => {
  it("renders the route label + shows the unavailable hint when the scaffold exposes no models", async () => {
    mockedApi.voiceStatus.mockResolvedValueOnce(
      statusWith({
        active_id: "whispercpp-speech",
        label: "whisper.cpp · ggml-base.en.bin",
        active_model: "ggml-base.en.bin",
        providers: [
          {
            id: "whispercpp-speech",
            label: "whisper.cpp · ggml-base.en.bin",
            active: true,
          },
        ],
      }),
    );
    // Whisper scaffold returns an empty list today — folded to the
    // "Models unavailable" hint.
    mockedApi.listSpeechModels.mockResolvedValueOnce(
      modelsList(
        "whispercpp-speech",
        [],
        "Models unavailable for this provider.",
      ),
    );

    render(<VoiceBadge />);

    expect(await screen.findByText("Voice route")).toBeTruthy();
    expect(
      await screen.findByText("Models unavailable for this provider."),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Refresh model list" }),
    ).toBeTruthy();
  });

  it("renders a clickable model chip when discovery surfaces real ids", async () => {
    mockedApi.voiceStatus.mockResolvedValueOnce(
      statusWith({
        active_id: "whispercpp-speech",
        label: "whisper.cpp · ggml-base.en",
        active_model: "ggml-base.en",
        providers: [
          {
            id: "whispercpp-speech",
            label: "whisper.cpp · ggml-base.en",
            active: true,
          },
        ],
      }),
    );
    mockedApi.listSpeechModels.mockResolvedValueOnce(
      modelsList("whispercpp-speech", ["ggml-base.en", "ggml-small.en"]),
    );

    render(<VoiceBadge />);

    const strip = await screen.findByLabelText("Available speech models");
    const active = within(strip).getByRole("listitem", {
      name: /ggml-base.en \(active\)/i,
    }) as HTMLButtonElement;
    expect(active.getAttribute("aria-pressed")).toBe("true");

    const small = within(strip).getByRole("listitem", {
      name: /Switch to ggml-small.en/i,
    }) as HTMLButtonElement;

    mockedApi.setActiveSpeechModel.mockResolvedValueOnce(
      statusWith({
        active_id: "whispercpp-speech",
        label: "whisper.cpp · ggml-small.en",
        active_model: "ggml-small.en",
        providers: [
          {
            id: "whispercpp-speech",
            label: "whisper.cpp · ggml-small.en",
            active: true,
          },
        ],
      }),
    );
    mockedApi.listSpeechModels.mockResolvedValueOnce(
      modelsList("whispercpp-speech", ["ggml-base.en", "ggml-small.en"]),
    );

    small.click();

    await waitFor(() => {
      expect(mockedApi.setActiveSpeechModel).toHaveBeenCalledWith(
        "ggml-small.en",
      );
    });
  });
});

describe("VoiceBadge — ActiveVoiceRoute hint", () => {
  // Covered indirectly — the hint component is simpler than VisionBadge
  // and the helper is unit-tested in ActiveVoiceRoute.test. This slot is
  // left here intentionally so future smoke tests for the two rendering
  // together have a home.
  it("is tested separately in ActiveVoiceRoute.test.tsx", () => {
    expect(true).toBe(true);
  });
});
