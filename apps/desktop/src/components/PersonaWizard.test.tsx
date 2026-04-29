// Component tests for PersonaWizard — the v0 onboarding pick-flow that
// reads bundled Tier-1 previews and lets the user choose 1 of 9
// personas.
//
// Mocks two browser surfaces:
//   - `fetch` for the /personas-previews/index.json catalog
//   - `Audio` for preview-clip playback (jsdom has no media stack)
//
// Assertions stay close to user-visible text and ARIA roles. Pixel
// layout, audio decoding, and Tauri commands are out of scope.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { PersonaWizard } from "./PersonaWizard";

const INDEX_PATH = "/personas-previews/index.json";

function indexFixture() {
  return {
    schema_version: 1,
    personas: [
      {
        slug: "aurora",
        display_name: "Aurora Nash",
        tagline: "Warm and grounded.",
        archetype: "warm_supportive",
        preview_webp: "aurora/preview.webp",
        preview_voice_opus: "aurora/preview_voice.opus",
      },
      {
        slug: "marcus_chen",
        display_name: "Marcus Chen",
        tagline: "Sharp and deliberate.",
        archetype: "analytical_focused",
        preview_webp: "marcus_chen/preview.webp",
        preview_voice_opus: "marcus_chen/preview_voice.opus",
      },
    ],
  };
}

function mockFetchIndex(body: unknown, ok = true) {
  return vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === INDEX_PATH) {
      return {
        ok,
        status: ok ? 200 : 500,
        statusText: ok ? "OK" : "Internal Server Error",
        json: async () => body,
      } as Response;
    }
    throw new Error(`unexpected fetch: ${String(input)}`);
  });
}

class FakeAudio {
  static instances: FakeAudio[] = [];
  src: string;
  onended: (() => void) | null = null;
  paused = true;
  currentTime = 0;
  played = false;
  constructor(src?: string) {
    this.src = src ?? "";
    FakeAudio.instances.push(this);
  }
  play() {
    this.played = true;
    this.paused = false;
    return Promise.resolve();
  }
  pause() {
    this.paused = true;
  }
}

beforeEach(() => {
  FakeAudio.instances = [];
  // jsdom doesn't ship a usable Audio constructor; install the fake.
  vi.stubGlobal("Audio", FakeAudio as unknown as typeof Audio);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("PersonaWizard", () => {
  it("renders a card per persona once the index loads", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    expect(await screen.findByText("Aurora Nash")).toBeTruthy();
    expect(screen.getByText("Marcus Chen")).toBeTruthy();
    // Tagline + archetype both surface so the user can compare cards.
    expect(screen.getByText("Warm and grounded.")).toBeTruthy();
    // archetype is rendered with underscores replaced.
    expect(screen.getByText("warm supportive")).toBeTruthy();
  });

  it("disables Continue until a card is picked, then enables it", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    const cta = (await screen.findByRole("button", {
      name: /pick a companion to continue/i,
    })) as HTMLButtonElement;
    expect(cta.disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /pick aurora nash/i }));

    const enabledCta = (await screen.findByRole("button", {
      name: /continue with aurora nash/i,
    })) as HTMLButtonElement;
    expect(enabledCta.disabled).toBe(false);
  });

  it("plays the persona's voice clip on selection and toggles aria-pressed", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    const card = (await screen.findByRole("button", {
      name: /pick marcus chen/i,
    })) as HTMLButtonElement;
    expect(card.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(card);

    await waitFor(() => {
      expect(card.getAttribute("aria-pressed")).toBe("true");
    });
    expect(FakeAudio.instances.length).toBe(1);
    expect(FakeAudio.instances[0].src).toContain(
      "/personas-previews/marcus_chen/preview_voice.opus",
    );
    expect(FakeAudio.instances[0].played).toBe(true);
  });

  it("stops the previous clip when a different card is picked", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    const aurora = await screen.findByRole("button", {
      name: /pick aurora nash/i,
    });
    fireEvent.click(aurora);
    await waitFor(() => expect(FakeAudio.instances.length).toBe(1));

    const marcus = screen.getByRole("button", { name: /pick marcus chen/i });
    fireEvent.click(marcus);

    await waitFor(() => expect(FakeAudio.instances.length).toBe(2));
    expect(FakeAudio.instances[0].paused).toBe(true);
    expect(FakeAudio.instances[1].played).toBe(true);
  });

  it("walks pick → confirm → commit and calls onCommit with the slug", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    const onCommit = vi.fn();
    render(<PersonaWizard onCommit={onCommit} />);

    fireEvent.click(
      await screen.findByRole("button", { name: /pick marcus chen/i }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: /continue with marcus chen/i,
      }),
    );

    // Confirmation step shows the picked persona and the download copy.
    expect(await screen.findByText(/you picked marcus chen/i)).toBeTruthy();
    expect(screen.getByText(/will download/i)).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", { name: /^continue with marcus$/i }),
    );

    expect(onCommit).toHaveBeenCalledWith("marcus_chen");
  });

  it("Back from confirmation returns to the pick step with the selection intact", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    fireEvent.click(
      await screen.findByRole("button", { name: /pick aurora nash/i }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: /continue with aurora nash/i,
      }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: /^back$/i }),
    );

    // Selection survives the round-trip: Continue is enabled, not disabled.
    const cta = (await screen.findByRole("button", {
      name: /continue with aurora nash/i,
    })) as HTMLButtonElement;
    expect(cta.disabled).toBe(false);
  });

  it("renders a wizard-blocking error when the index fetch fails", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(null, false));
    render(<PersonaWizard onCommit={() => {}} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/couldn't load companions/i);
    expect(alert.textContent).toMatch(/build-persona-previews/i);
  });

  it("rejects an index payload missing the personas array", async () => {
    vi.stubGlobal("fetch", mockFetchIndex({ schema_version: 1 }));
    render(<PersonaWizard onCommit={() => {}} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/unexpected shape/i);
  });

  it("filters the rendered cast to availableSlugs when provided", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} availableSlugs={["aurora"]} />);

    expect(await screen.findByText("Aurora Nash")).toBeTruthy();
    expect(screen.queryByText("Marcus Chen")).toBeNull();
  });

  it("uses the singular companion headline when only one persona is available", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} availableSlugs={["aurora"]} />);

    expect(await screen.findByText(/meet your companion/i)).toBeTruthy();
  });

  it("renders the no-companions-available state when the filter empties the cast", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} availableSlugs={[]} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/no companions available yet/i);
  });

  it("uses a roving tabindex so only one card is in the tab order", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    const aurora = (await screen.findByRole("button", {
      name: /pick aurora nash/i,
    })) as HTMLButtonElement;
    const marcus = screen.getByRole("button", {
      name: /pick marcus chen/i,
    }) as HTMLButtonElement;

    // First card is the rover by default; the rest opt out of Tab.
    expect(aurora.tabIndex).toBe(0);
    expect(marcus.tabIndex).toBe(-1);
  });

  it("ArrowRight moves focus + roving tabindex to the next card", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    const aurora = (await screen.findByRole("button", {
      name: /pick aurora nash/i,
    })) as HTMLButtonElement;
    const marcus = screen.getByRole("button", {
      name: /pick marcus chen/i,
    }) as HTMLButtonElement;
    const grid = screen.getByRole("grid");

    aurora.focus();
    fireEvent.keyDown(grid, { key: "ArrowRight" });

    await waitFor(() => {
      expect(marcus.tabIndex).toBe(0);
      expect(aurora.tabIndex).toBe(-1);
      expect(document.activeElement).toBe(marcus);
    });
  });

  it("ArrowLeft from the first card wraps to the last", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    const aurora = (await screen.findByRole("button", {
      name: /pick aurora nash/i,
    })) as HTMLButtonElement;
    const marcus = screen.getByRole("button", {
      name: /pick marcus chen/i,
    }) as HTMLButtonElement;
    const grid = screen.getByRole("grid");

    aurora.focus();
    fireEvent.keyDown(grid, { key: "ArrowLeft" });

    await waitFor(() => {
      expect(document.activeElement).toBe(marcus);
    });
  });

  it("End jumps focus to the last card, Home returns it to the first", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    const aurora = (await screen.findByRole("button", {
      name: /pick aurora nash/i,
    })) as HTMLButtonElement;
    const marcus = screen.getByRole("button", {
      name: /pick marcus chen/i,
    }) as HTMLButtonElement;
    const grid = screen.getByRole("grid");

    aurora.focus();
    fireEvent.keyDown(grid, { key: "End" });
    await waitFor(() => expect(document.activeElement).toBe(marcus));

    fireEvent.keyDown(grid, { key: "Home" });
    await waitFor(() => expect(document.activeElement).toBe(aurora));
  });

  it("renders an aria-labelled voice-playing indicator while a clip plays", async () => {
    vi.stubGlobal("fetch", mockFetchIndex(indexFixture()));
    render(<PersonaWizard onCommit={() => {}} />);

    fireEvent.click(
      await screen.findByRole("button", { name: /pick aurora nash/i }),
    );

    expect(
      await screen.findByLabelText(/voice preview playing/i),
    ).toBeTruthy();
  });
});
