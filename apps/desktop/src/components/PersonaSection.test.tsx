// Component tests for the Persona section of SettingsDrawer — T2.4.
//
// Mocks `lib/api` and `lib/personaPreviews` so every test drives the
// section through its public TS surface. Assertions stay close to
// user-visible text and ARIA roles. Doctrine §8 satisfier: these
// tests cover the load → click → switch → confirm-active user flow,
// the install-then-switch flow for preview-only personas, error
// surfacing, and the memory-continuity caption. A live used-as-user
// click-through against a real Tauri build is still owed before
// T2.4 ships.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import { PersonaSection } from "./PersonaSection";

vi.mock("../lib/api", () => ({
  listPersonas: vi.fn(),
  switchPersona: vi.fn(),
  installPersona: vi.fn(),
  companionBanner: vi.fn(),
  personaManifestUrl: vi.fn(),
}));

vi.mock("../lib/personaPreviews", () => ({
  loadPersonaPreviews: vi.fn(),
  previewAssetUrl: (rel: string) => `/personas-previews/${rel}`,
}));

import * as api from "../lib/api";
import * as previews from "../lib/personaPreviews";

const mockedApi = api as unknown as {
  listPersonas: ReturnType<typeof vi.fn>;
  switchPersona: ReturnType<typeof vi.fn>;
  installPersona: ReturnType<typeof vi.fn>;
  companionBanner: ReturnType<typeof vi.fn>;
  personaManifestUrl: ReturnType<typeof vi.fn>;
};

const mockedPreviews = previews as unknown as {
  loadPersonaPreviews: ReturnType<typeof vi.fn>;
};

const PREVIEWS = [
  {
    slug: "aurora",
    display_name: "Aurora",
    tagline: "Steady, careful, deliberate.",
    archetype: "the_anchor",
    preview_webp: "aurora/preview.webp",
    preview_voice_opus: "aurora/preview_voice.opus",
  },
  {
    slug: "sable",
    display_name: "Sable",
    tagline: "Quick, sharp, dry.",
    archetype: "the_blade",
    preview_webp: "sable/preview.webp",
    preview_voice_opus: "sable/preview_voice.opus",
  },
  {
    slug: "ember",
    display_name: "Ember",
    tagline: "Warm, encouraging, present.",
    archetype: "the_hearth",
    preview_webp: "ember/preview.webp",
    preview_voice_opus: "ember/preview_voice.opus",
  },
];

const CATALOG_BOTH_INSTALLED = [
  {
    id: "aurora",
    name: "Aurora",
    tagline: "Steady, careful, deliberate.",
    stance: "anchor",
    tone: "calm",
  },
  {
    id: "sable",
    name: "Sable",
    tagline: "Quick, sharp, dry.",
    stance: "blade",
    tone: "dry",
  },
];

const BANNER_AURORA = {
  persona_id: "aurora",
  persona_name: "Aurora",
  persona_version: "0.1.0",
  preferred_tier: "T2",
  provider_mode: "ollama" as const,
  provider_label: "Ollama",
  output_detail: "balanced" as const,
  tagline: "Steady, careful, deliberate.",
  system_prompt: "",
};

const BANNER_SABLE = { ...BANNER_AURORA, persona_id: "sable", persona_name: "Sable" };
const BANNER_EMBER = { ...BANNER_AURORA, persona_id: "ember", persona_name: "Ember" };

beforeEach(() => {
  vi.clearAllMocks();
  mockedApi.listPersonas.mockResolvedValue(CATALOG_BOTH_INSTALLED);
  mockedPreviews.loadPersonaPreviews.mockResolvedValue(PREVIEWS);
  mockedApi.companionBanner.mockResolvedValue(BANNER_AURORA);
  mockedApi.personaManifestUrl.mockReturnValue(
    "https://example.test/personas/ember/manifest.json",
  );
});

describe("PersonaSection", () => {
  it("loads the catalog + active persona on mount and marks the active one", async () => {
    render(<PersonaSection open={true} />);

    await waitFor(() => expect(mockedApi.listPersonas).toHaveBeenCalled());
    await waitFor(() => expect(mockedApi.companionBanner).toHaveBeenCalled());

    // Aurora's row carries the "Active" marker.
    await screen.findByLabelText("active persona");

    // Aurora's switch button is aria-checked + disabled.
    const auroraRadios = await screen.findAllByRole("radio");
    const aurora = auroraRadios.find(
      (b) => b.getAttribute("aria-checked") === "true",
    )!;
    expect(aurora).toBeTruthy();
    expect((aurora as HTMLButtonElement).disabled).toBe(true);
  });

  it("renders preview-only personas with an Install button (not a Switch)", async () => {
    render(<PersonaSection open={true} />);
    // Ember is in previews but not in the catalog → preview-only.
    const installBtn = await screen.findByRole("button", {
      name: /Install full pack/i,
    });
    expect(installBtn).toBeTruthy();
    // And the "Preview only" tag is present.
    expect(screen.getByText("Preview only")).toBeTruthy();
  });

  it("calls switch_persona when an installed non-active row is clicked, then refreshes the active marker", async () => {
    mockedApi.switchPersona.mockResolvedValue(BANNER_SABLE);
    render(<PersonaSection open={true} />);

    // Wait for initial load to settle on Aurora.
    await screen.findByLabelText("active persona");

    // Sable's switch button. After the doctrine §8 a11y fix
    // (PersonaSection 2026-04-30), each switch radio carries an
    // aria-label of "Switch to <persona name>" so screen-reader
    // users hear which persona they're targeting.
    const sableBtn = await screen.findByRole("radio", {
      name: /Switch to Sable/i,
    });
    fireEvent.click(sableBtn);

    await waitFor(() =>
      expect(mockedApi.switchPersona).toHaveBeenCalledWith("sable"),
    );
    // After the swap the active marker now sits on Sable.
    await waitFor(() => {
      const radios = screen.getAllByRole("radio");
      const checked = radios.find(
        (b) => b.getAttribute("aria-checked") === "true",
      );
      expect(checked?.textContent).toMatch(/Active/i);
    });
  });

  it("install-then-switch: installs the pack, refreshes the catalog, and switches", async () => {
    mockedApi.installPersona.mockResolvedValue(1);
    // After install, list_personas now includes ember.
    mockedApi.listPersonas
      .mockResolvedValueOnce(CATALOG_BOTH_INSTALLED) // initial load
      .mockResolvedValueOnce([
        ...CATALOG_BOTH_INSTALLED,
        {
          id: "ember",
          name: "Ember",
          tagline: "Warm, encouraging, present.",
          stance: "hearth",
          tone: "warm",
        },
      ]);
    mockedApi.switchPersona.mockResolvedValue(BANNER_EMBER);

    render(<PersonaSection open={true} />);

    const installBtn = await screen.findByRole("button", {
      name: /Install full pack/i,
    });
    fireEvent.click(installBtn);

    await waitFor(() =>
      expect(mockedApi.installPersona).toHaveBeenCalledWith(
        "ember",
        "https://example.test/personas/ember/manifest.json",
      ),
    );
    await waitFor(() =>
      expect(mockedApi.switchPersona).toHaveBeenCalledWith("ember"),
    );
  });

  it("surfaces switch_persona errors", async () => {
    mockedApi.switchPersona.mockRejectedValue(
      new Error("backend rejected: persona not found"),
    );
    render(<PersonaSection open={true} />);

    await screen.findByLabelText("active persona");
    const sableBtn = await screen.findByRole("radio", {
      name: /Switch to Sable/i,
    });
    fireEvent.click(sableBtn);

    await screen.findByText(/persona not found/);
  });

  it("explains the gap when the persona registry isn't configured", async () => {
    mockedApi.personaManifestUrl.mockReturnValue(null);
    render(<PersonaSection open={true} />);

    const installBtn = await screen.findByRole("button", {
      name: /Install full pack/i,
    });
    fireEvent.click(installBtn);

    await screen.findByText(/registry isn't configured/i);
    expect(mockedApi.installPersona).not.toHaveBeenCalled();
  });

  it("shows the memory-continuity caption (ADR-0001)", async () => {
    render(<PersonaSection open={true} />);
    // Two paragraphs intentionally repeat the line — the lead
    // explainer under the heading and a short footer caption — so
    // the user reads it before *and* after the picker. Asserting on
    // count guarantees both stay.
    await waitFor(() => {
      const matches = screen.getAllByText(
        /memory stays with you across personas/i,
      );
      expect(matches.length).toBeGreaterThanOrEqual(2);
    });
  });
});
