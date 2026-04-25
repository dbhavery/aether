// Smoke tests for RetrievalTab — Session B scaffold landing.
//
// Mocks the lib/api module so tests drive the tab through the
// embeddingsReadiness() / getTier() surface only. Assertions stay
// at the user-visible text level — implementation details (poll
// interval, internal state) are not the contract under test.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { RetrievalTab } from "./RetrievalTab";
import type { ReadinessState, TierConfig } from "../lib/types";

vi.mock("../lib/api", () => ({
  embeddingsReadiness: vi.fn(),
  getTier: vi.fn(),
}));

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  embeddingsReadiness: ReturnType<typeof vi.fn>;
  getTier: ReturnType<typeof vi.fn>;
};

const TIER_FLAME: TierConfig = {
  selected_tier: "flame",
  detected_tier: "flame",
  detected_at_ms: 1_700_000_000_000,
  manual_override: false,
  hardware_snapshot: {
    gpu: null,
    total_ram_gb: 32,
    cpu_cores: 16,
    disk_available_gb: 500,
    ollama_gpu_loaded: true,
    detected_at_ms: 1_700_000_000_000,
  },
};

beforeEach(() => {
  mockedApi.embeddingsReadiness.mockReset();
  mockedApi.getTier.mockReset();
  mockedApi.getTier.mockResolvedValue(TIER_FLAME);
});

describe("RetrievalTab", () => {
  it("renders the disabled state when embeddings are off", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "disabled" } as ReadinessState);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Retrieval is off/)).toBeTruthy();
    });
    expect(screen.getByText(/Active tier:/)).toBeTruthy();
  });

  it("renders the ready state when retrieval is active", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Retrieval is active/)).toBeTruthy();
    });
  });

  it("renders the model-not-installed reason with pull instruction", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({
      kind: "not_ready",
      reason: { kind: "model_not_installed", model: "bge-m3" },
    } as ReadinessState);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Retrieval is not active/)).toBeTruthy();
    });
    expect(screen.getByText(/ollama pull bge-m3/)).toBeTruthy();
  });

  it("renders the provider-unreachable reason", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({
      kind: "not_ready",
      reason: { kind: "provider_unreachable", detail: "connection refused" },
    } as ReadinessState);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/provider unreachable/i)).toBeTruthy();
    });
  });

  it("renders the bailout reason", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({
      kind: "not_ready",
      reason: { kind: "bailout" },
    } as ReadinessState);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/exceeded the 5-second wall-clock deadline/)).toBeTruthy();
    });
  });

  it("renders the low-disk reason with the gap copy", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({
      kind: "not_ready",
      reason: { kind: "low_disk", needed_gb: 2, available_gb: 1 },
    } as ReadinessState);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Need ~2 GB free; have ~1 GB/)).toBeTruthy();
    });
  });
});
