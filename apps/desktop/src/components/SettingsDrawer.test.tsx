// Component tests for the SettingsDrawer Autonomy section — T2.3.
//
// Mocks `lib/api` so every test drives the drawer through the TS client
// surface. Assertions stay close to user-visible text and ARIA roles.
// Other panels (Media, Microphone, Presence, Memory) are exercised
// through their respective api fetches but only their existence is
// asserted — the contract under test here is the Autonomy preset row.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import { SettingsDrawer } from "./SettingsDrawer";

vi.mock("../lib/api", () => ({
  getMediaPermissions: vi.fn(),
  getMemoryConfig: vi.fn(),
  getMicPermission: vi.fn(),
  getPresenceConfig: vi.fn(),
  setMediaPermission: vi.fn(),
  setMemoryConfig: vi.fn(),
  setMicPermission: vi.fn(),
  setPresenceConfig: vi.fn(),
  currentAutonomyPreset: vi.fn(),
  setAutonomyPreset: vi.fn(),
  // T2.4 — PersonaSection ships inside SettingsDrawer. Stub its
  // backend calls so the parent test stays focused on the Autonomy
  // contract.
  listPersonas: vi.fn().mockResolvedValue([]),
  switchPersona: vi.fn(),
  installPersona: vi.fn(),
  companionBanner: vi.fn().mockResolvedValue({
    persona_id: "aurora",
    persona_name: "Aurora",
    persona_version: "0.1.0",
    preferred_tier: "T2",
    provider_mode: "ollama",
    provider_label: "Ollama",
    output_detail: "balanced",
    tagline: "",
    system_prompt: "",
  }),
  personaManifestUrl: vi.fn().mockReturnValue(null),
}));

vi.mock("../lib/personaPreviews", () => ({
  loadPersonaPreviews: vi.fn().mockResolvedValue([]),
  previewAssetUrl: (rel: string) => `/personas-previews/${rel}`,
}));

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  getMediaPermissions: ReturnType<typeof vi.fn>;
  getMemoryConfig: ReturnType<typeof vi.fn>;
  getMicPermission: ReturnType<typeof vi.fn>;
  getPresenceConfig: ReturnType<typeof vi.fn>;
  setMediaPermission: ReturnType<typeof vi.fn>;
  setMemoryConfig: ReturnType<typeof vi.fn>;
  setMicPermission: ReturnType<typeof vi.fn>;
  setPresenceConfig: ReturnType<typeof vi.fn>;
  currentAutonomyPreset: ReturnType<typeof vi.fn>;
  setAutonomyPreset: ReturnType<typeof vi.fn>;
};

function defaultPanelMocks() {
  mockedApi.getMediaPermissions.mockResolvedValue({
    camera: "ask",
    screen: "ask",
  });
  mockedApi.getMicPermission.mockResolvedValue({ state: "ask" });
  mockedApi.getPresenceConfig.mockResolvedValue({
    enabled: true,
    history_in_trust_drawer: true,
    idle_after_s: 60,
    away_after_s: 300,
  });
  mockedApi.getMemoryConfig.mockResolvedValue({
    default_risk: {
      session: "auto",
      durable: "auto",
      facts: "ask",
      projects: "auto",
      preferences: "auto",
      artifacts: "ask",
    },
    retention_days: {
      session: null,
      durable: 30,
      facts: null,
      projects: null,
      preferences: null,
      artifacts: null,
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  defaultPanelMocks();
});

describe("SettingsDrawer Autonomy section", () => {
  it("does not render when closed", () => {
    render(<SettingsDrawer open={false} onClose={() => {}} />);
    expect(screen.queryByText("Autonomy")).toBeNull();
  });

  it("loads the current preset on open and reflects it in the row", async () => {
    mockedApi.currentAutonomyPreset.mockResolvedValue("operator");
    render(<SettingsDrawer open={true} onClose={() => {}} />);

    await waitFor(() =>
      expect(mockedApi.currentAutonomyPreset).toHaveBeenCalled(),
    );
    const operator = await screen.findByRole("radio", { name: "Operator" });
    await waitFor(() =>
      expect(operator.getAttribute("aria-checked")).toBe("true"),
    );
  });

  it("treats null backend value as 'No override'", async () => {
    mockedApi.currentAutonomyPreset.mockResolvedValue(null);
    render(<SettingsDrawer open={true} onClose={() => {}} />);

    const noOverride = await screen.findByRole("radio", { name: "No override" });
    await waitFor(() =>
      expect(noOverride.getAttribute("aria-checked")).toBe("true"),
    );
  });

  it("calls set_autonomy_preset with the wire string when a preset is chosen", async () => {
    mockedApi.currentAutonomyPreset.mockResolvedValue(null);
    mockedApi.setAutonomyPreset.mockResolvedValue({ slug: "aurora" });
    render(<SettingsDrawer open={true} onClose={() => {}} />);

    const observer = await screen.findByRole("radio", { name: "Observer" });
    fireEvent.click(observer);

    await waitFor(() =>
      expect(mockedApi.setAutonomyPreset).toHaveBeenCalledWith("observer"),
    );
    await waitFor(() =>
      expect(observer.getAttribute("aria-checked")).toBe("true"),
    );
  });

  it("clears the overlay (passes null) when 'No override' is chosen", async () => {
    mockedApi.currentAutonomyPreset.mockResolvedValue("assistant");
    mockedApi.setAutonomyPreset.mockResolvedValue({ slug: "aurora" });
    render(<SettingsDrawer open={true} onClose={() => {}} />);

    const noOverride = await screen.findByRole("radio", { name: "No override" });
    fireEvent.click(noOverride);

    await waitFor(() =>
      expect(mockedApi.setAutonomyPreset).toHaveBeenCalledWith(null),
    );
  });

  it("surfaces the error when set_autonomy_preset rejects", async () => {
    mockedApi.currentAutonomyPreset.mockResolvedValue(null);
    mockedApi.setAutonomyPreset.mockRejectedValue(
      new Error("backend rejected: unknown autonomy preset"),
    );
    render(<SettingsDrawer open={true} onClose={() => {}} />);

    const operator = await screen.findByRole("radio", { name: "Operator" });
    fireEvent.click(operator);

    await screen.findByText(/backend rejected/);
  });

  it("disables the radio buttons until the backend value resolves", async () => {
    let resolve!: (v: string | null) => void;
    mockedApi.currentAutonomyPreset.mockReturnValue(
      new Promise<string | null>((r) => {
        resolve = r;
      }),
    );
    render(<SettingsDrawer open={true} onClose={() => {}} />);

    const observer = await screen.findByRole("radio", { name: "Observer" });
    expect((observer as HTMLButtonElement).disabled).toBe(true);

    resolve("assistant");
    await waitFor(() =>
      expect((observer as HTMLButtonElement).disabled).toBe(false),
    );
  });
});
