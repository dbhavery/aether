// Component tests for VisionBadge — the runtime swap surface for
// vision providers + per-provider model selection.
//
// We mock `../lib/api` so the badge sees deterministic responses for
// `visionStatus`, `listVisionModels`, `setActiveVisionProvider`,
// `setActiveVisionModel`, and `refreshVisionModels`. No Tauri runtime
// is needed; assertions stay close to user-visible text and roles.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";

import { VisionBadge } from "./VisionBadge";
import type { VisionModelList, VisionStatus } from "../lib/types";

vi.mock("../lib/api", () => {
  return {
    visionStatus: vi.fn(),
    listVisionModels: vi.fn(),
    refreshVisionModels: vi.fn(),
    setActiveVisionProvider: vi.fn(),
    setActiveVisionModel: vi.fn(),
  };
});

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  visionStatus: ReturnType<typeof vi.fn>;
  listVisionModels: ReturnType<typeof vi.fn>;
  refreshVisionModels: ReturnType<typeof vi.fn>;
  setActiveVisionProvider: ReturnType<typeof vi.fn>;
  setActiveVisionModel: ReturnType<typeof vi.fn>;
};

const TEXT_ONLY_FALLBACK: VisionStatus = {
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
  providers?: VisionStatus["providers"];
}): VisionStatus {
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
): VisionModelList {
  return { provider_id, models, error };
}

beforeEach(() => {
  for (const k of Object.keys(mockedApi) as (keyof typeof mockedApi)[]) {
    mockedApi[k].mockReset();
  }
});

describe("VisionBadge — text-only fallback", () => {
  it("renders honest fallback copy when no providers are registered", async () => {
    mockedApi.visionStatus.mockResolvedValueOnce(TEXT_ONLY_FALLBACK);

    render(<VisionBadge />);

    expect(await screen.findByText("Text-only fallback")).toBeTruthy();
    // Fallback should explain how to enable a vision provider.
    expect(
      screen.getByText(/AETHER_OLLAMA_VISION_MODEL/i),
    ).toBeTruthy();
    expect(
      screen.getByText(/AETHER_LLAMACPP_VISION_MODEL/i),
    ).toBeTruthy();
    // No model strip in this state.
    expect(screen.queryByLabelText("Available models")).toBeNull();
    // listVisionModels MUST NOT be called when there's no active id.
    expect(mockedApi.listVisionModels).not.toHaveBeenCalled();
  });

  it("falls back to a hard-coded text-only state when visionStatus rejects", async () => {
    mockedApi.visionStatus.mockRejectedValueOnce(new Error("boom"));

    render(<VisionBadge />);

    expect(await screen.findByText("Text-only fallback")).toBeTruthy();
    expect(mockedApi.listVisionModels).not.toHaveBeenCalled();
  });
});

describe("VisionBadge — active provider with models", () => {
  it("renders the model strip with the active model marked active", async () => {
    mockedApi.visionStatus.mockResolvedValueOnce(
      statusWith({
        active_id: "ollama-vision",
        label: "Ollama vision · llava:latest · http://127.0.0.1:11434",
        active_model: "llava:latest",
        providers: [
          {
            id: "ollama-vision",
            label: "Ollama vision · llava:latest",
            active: true,
          },
        ],
      }),
    );
    mockedApi.listVisionModels.mockResolvedValueOnce(
      modelsList("ollama-vision", ["llava:latest", "gemma3:vision"]),
    );

    render(<VisionBadge />);

    expect(await screen.findByText("Vision route")).toBeTruthy();
    const strip = await screen.findByLabelText("Available models");
    const llava = within(strip).getByRole("listitem", {
      name: /llava:latest \(active\)/i,
    }) as HTMLButtonElement;
    expect(llava.getAttribute("aria-pressed")).toBe("true");
    expect(llava.disabled).toBe(true);

    const gemma = within(strip).getByRole("listitem", {
      name: /Switch to gemma3:vision/i,
    }) as HTMLButtonElement;
    expect(gemma.getAttribute("aria-pressed")).toBe("false");
    expect(gemma.disabled).toBe(false);
  });

  it("renders the unavailable hint and the refresh button when discovery is empty", async () => {
    mockedApi.visionStatus.mockResolvedValueOnce(
      statusWith({
        active_id: "llamacpp-vision",
        label: "llama.cpp vision · llava-v1.6 · http://127.0.0.1:8080",
        active_model: "llava-v1.6",
        providers: [
          {
            id: "llamacpp-vision",
            label: "llama.cpp vision · llava-v1.6",
            active: true,
          },
        ],
      }),
    );
    mockedApi.listVisionModels.mockResolvedValueOnce(
      modelsList("llamacpp-vision", [], "Models unavailable for this provider."),
    );

    render(<VisionBadge />);

    expect(
      await screen.findByText("Models unavailable for this provider."),
    ).toBeTruthy();
    // Refresh button still present so the user can retry.
    expect(screen.getByRole("button", { name: "Refresh model list" })).toBeTruthy();
    // No model strip rendered when models are empty.
    expect(screen.queryByLabelText("Available models")).toBeNull();
  });
});

describe("VisionBadge — interactions", () => {
  it("clicking a model chip calls setActiveVisionModel and re-renders with the new active ring", async () => {
    mockedApi.visionStatus.mockResolvedValueOnce(
      statusWith({
        active_id: "ollama-vision",
        label: "Ollama · llava",
        active_model: "llava:latest",
        providers: [
          { id: "ollama-vision", label: "Ollama · llava", active: true },
        ],
      }),
    );
    mockedApi.listVisionModels.mockResolvedValueOnce(
      modelsList("ollama-vision", ["llava:latest", "gemma3:vision"]),
    );

    const { findByLabelText } = render(<VisionBadge />);

    const strip = await findByLabelText("Available models");
    const gemma = within(strip).getByRole("listitem", {
      name: /Switch to gemma3:vision/i,
    }) as HTMLButtonElement;

    // Set up the response the click triggers: status now reports
    // gemma3 as the active model, and listVisionModels gets called
    // again to refresh the chip ring.
    mockedApi.setActiveVisionModel.mockResolvedValueOnce(
      statusWith({
        active_id: "ollama-vision",
        label: "Ollama · gemma3",
        active_model: "gemma3:vision",
        providers: [
          { id: "ollama-vision", label: "Ollama · gemma3", active: true },
        ],
      }),
    );
    mockedApi.listVisionModels.mockResolvedValueOnce(
      modelsList("ollama-vision", ["llava:latest", "gemma3:vision"]),
    );

    gemma.click();

    await waitFor(() => {
      expect(mockedApi.setActiveVisionModel).toHaveBeenCalledWith("gemma3:vision");
    });
    await waitFor(() => {
      const updated = screen.getByRole("listitem", {
        name: /gemma3:vision \(active\)/i,
      }) as HTMLButtonElement;
      expect(updated.getAttribute("aria-pressed")).toBe("true");
    });
  });

  it("clicking refresh calls refreshVisionModels and re-renders the strip", async () => {
    mockedApi.visionStatus.mockResolvedValueOnce(
      statusWith({
        active_id: "ollama-vision",
        label: "Ollama · llava",
        active_model: "llava:latest",
        providers: [
          { id: "ollama-vision", label: "Ollama · llava", active: true },
        ],
      }),
    );
    mockedApi.listVisionModels.mockResolvedValueOnce(
      modelsList("ollama-vision", ["llava:latest"]),
    );

    render(<VisionBadge />);

    // Wait for the initial chip to settle.
    await screen.findByRole("listitem", { name: /llava:latest \(active\)/i });

    mockedApi.refreshVisionModels.mockResolvedValueOnce(
      modelsList("ollama-vision", ["llava:latest", "gemma3:vision"]),
    );

    const refresh = screen.getByRole("button", { name: "Refresh model list" });
    refresh.click();

    await waitFor(() => {
      expect(mockedApi.refreshVisionModels).toHaveBeenCalledTimes(1);
    });
    // The new model should appear after the refresh resolves.
    await screen.findByRole("listitem", { name: /Switch to gemma3:vision/i });
  });

  it("renders the error line when setActiveVisionModel rejects, then re-enables chips", async () => {
    mockedApi.visionStatus.mockResolvedValueOnce(
      statusWith({
        active_id: "ollama-vision",
        label: "Ollama · llava",
        active_model: "llava:latest",
        providers: [
          { id: "ollama-vision", label: "Ollama · llava", active: true },
        ],
      }),
    );
    mockedApi.listVisionModels.mockResolvedValueOnce(
      modelsList("ollama-vision", ["llava:latest", "gemma3:vision"]),
    );

    render(<VisionBadge />);

    const gemma = (await screen.findByRole("listitem", {
      name: /Switch to gemma3:vision/i,
    })) as HTMLButtonElement;

    mockedApi.setActiveVisionModel.mockRejectedValueOnce(
      new Error("unknown model for active provider: gemma3:vision"),
    );

    gemma.click();

    await screen.findByText(/unknown model for active provider/);
    // After the failure, gemma should be clickable again (busy released).
    await waitFor(() => {
      const reEnabled = screen.getByRole("listitem", {
        name: /Switch to gemma3:vision/i,
      }) as HTMLButtonElement;
      expect(reEnabled.disabled).toBe(false);
    });
  });
});
