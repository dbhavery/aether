// Smoke tests for ReadinessIndicator — Session B scaffold landing.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { ReadinessIndicator } from "./ReadinessIndicator";
import type { ReadinessState } from "../lib/types";

vi.mock("../lib/api", () => ({
  embeddingsReadiness: vi.fn(),
}));

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  embeddingsReadiness: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  mockedApi.embeddingsReadiness.mockReset();
});

describe("ReadinessIndicator", () => {
  it("hides the dot when retrieval is ready", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    const { container } = render(<ReadinessIndicator />);
    await waitFor(() => {
      expect(mockedApi.embeddingsReadiness).toHaveBeenCalled();
    });
    // Dot rendered as a sized span; ready means no dot.
    expect(container.querySelector(".rounded-full")).toBeNull();
  });

  it("hides the dot when retrieval is intentionally disabled", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "disabled" } as ReadinessState);
    const { container } = render(<ReadinessIndicator />);
    await waitFor(() => expect(mockedApi.embeddingsReadiness).toHaveBeenCalled());
    expect(container.querySelector(".rounded-full")).toBeNull();
  });

  it("shows a warn dot when retrieval is not ready", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({
      kind: "not_ready",
      reason: { kind: "provider_unreachable", detail: "x" },
    } as ReadinessState);
    const { container } = render(<ReadinessIndicator />);
    await waitFor(() => {
      expect(container.querySelector(".rounded-full")).not.toBeNull();
    });
    const dot = container.querySelector(".rounded-full")!;
    expect(dot.className).toContain("bg-aether-warn");
  });

  it("wraps children and overlays the dot when not_ready", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({
      kind: "not_ready",
      reason: { kind: "bailout" },
    } as ReadinessState);
    render(
      <ReadinessIndicator>
        <button>anchor</button>
      </ReadinessIndicator>,
    );
    await waitFor(() => expect(screen.getByText("anchor")).toBeTruthy());
    expect(screen.getByLabelText("retrieval not ready")).toBeTruthy();
  });
});
