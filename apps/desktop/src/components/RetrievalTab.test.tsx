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
  getMemoryConfig: vi.fn(),
  backfillCount: vi.fn(),
  backfillStatus: vi.fn(),
  cancelBackfill: vi.fn(),
  startBackfill: vi.fn(),
  onBackfillProgress: vi.fn(),
  onBackfillDone: vi.fn(),
  onTierChanged: vi.fn(),
}));

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  embeddingsReadiness: ReturnType<typeof vi.fn>;
  getTier: ReturnType<typeof vi.fn>;
  getMemoryConfig: ReturnType<typeof vi.fn>;
  backfillCount: ReturnType<typeof vi.fn>;
  backfillStatus: ReturnType<typeof vi.fn>;
  cancelBackfill: ReturnType<typeof vi.fn>;
  startBackfill: ReturnType<typeof vi.fn>;
  onBackfillProgress: ReturnType<typeof vi.fn>;
  onBackfillDone: ReturnType<typeof vi.fn>;
  onTierChanged: ReturnType<typeof vi.fn>;
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
  mockedApi.backfillCount.mockReset();
  mockedApi.backfillStatus.mockReset();
  mockedApi.cancelBackfill.mockReset();
  mockedApi.startBackfill.mockReset();
  mockedApi.onBackfillProgress.mockReset();
  mockedApi.onBackfillDone.mockReset();
  mockedApi.getTier.mockResolvedValue(TIER_FLAME);
  mockedApi.getMemoryConfig.mockReset();
  mockedApi.getMemoryConfig.mockResolvedValue({
    retention_days: {},
    default_risk: {},
    embeddings: { enabled: true, provider: null },
    retrieval: { max_items: 5 },
  });
  mockedApi.backfillCount.mockResolvedValue(0);
  mockedApi.backfillStatus.mockResolvedValue({
    finished: true,
    cancelled: false,
    total: 0,
    completed: 0,
    failures: 0,
    current_domain: null,
    started_at_ms: 0,
  });
  mockedApi.onBackfillProgress.mockResolvedValue(() => {});
  mockedApi.onBackfillDone.mockResolvedValue(() => {});
  mockedApi.onTierChanged.mockReset();
  mockedApi.onTierChanged.mockResolvedValue(() => {});
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

  it("renders the backfill offer when ready and unembedded count > 0", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    mockedApi.backfillCount.mockResolvedValue(7);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Retrieval is active/)).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getByText(/7 memories not indexed for retrieval/)).toBeTruthy();
    });
    expect(screen.getByRole("button", { name: /Backfill now/ })).toBeTruthy();
  });

  it("hides the backfill offer when count is zero", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    mockedApi.backfillCount.mockResolvedValue(0);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Retrieval is active/)).toBeTruthy();
    });
    // No "memories not indexed" copy when count is zero.
    expect(screen.queryByText(/not indexed for retrieval/)).toBeNull();
  });

  it("uses singular noun when exactly one memory is unindexed", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    mockedApi.backfillCount.mockResolvedValue(1);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/1 memory not indexed for retrieval/)).toBeTruthy();
    });
  });

  it("displays the user-configured model when memory.embeddings.provider is set", async () => {
    // Active-model resolution: user's explicit provider wins over the
    // tier default. Critical for not-lying-to-the-user UX.
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    mockedApi.getMemoryConfig.mockResolvedValue({
      retention_days: {},
      default_risk: {},
      embeddings: { enabled: true, provider: "ollama:custom-model-name" },
      retrieval: { max_items: 5 },
    });
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/custom-model-name/)).toBeTruthy();
    });
  });

  it("falls back to tier default model when no provider configured", async () => {
    // Flame tier from beforeEach setup; no provider in memory config.
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Retrieval is active/)).toBeTruthy();
    });
    // Flame default per ADR-0007 D7 = bge-m3.
    expect(screen.getByText(/bge-m3/)).toBeTruthy();
  });

  it("strips provider prefix to display the bare model name", async () => {
    // bareModelName helper: "ollama:bge-m3" -> "bge-m3" displayed.
    mockedApi.embeddingsReadiness.mockResolvedValue({
      kind: "not_ready",
      reason: { kind: "model_not_installed", model: "" }, // empty model -> falls to bare name from config
    } as ReadinessState);
    mockedApi.getMemoryConfig.mockResolvedValue({
      retention_days: {},
      default_risk: {},
      embeddings: { enabled: true, provider: "ollama:fancy-embed-2026" },
      retrieval: { max_items: 5 },
    });
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      // The bare name appears in both the reason copy and the
      // "Target model: <code>X</code>" footer; either is sufficient
      // proof the prefix was stripped.
      expect(screen.getAllByText(/fancy-embed-2026/).length).toBeGreaterThan(0);
    });
  });
});
