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
    recovered_failures: 0,
    skipped_already_embedded: 0,
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

  it("surfaces skipped-already-embedded count in the post-run summary", async () => {
    // Second-pass backfill (after EmbeddingStore::embedded_ids fast
    // path) reports skipped > 0. The Last-backfill summary must
    // expose that number so the user understands why "indexed" is low.
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    mockedApi.backfillCount.mockResolvedValue(0);
    mockedApi.backfillStatus.mockResolvedValue({
      finished: true,
      cancelled: false,
      total: 5,
      completed: 0,
      failures: 0,
      recovered_failures: 0,
      skipped_already_embedded: 5,
      current_domain: null,
      started_at_ms: 0,
    });
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Retrieval is active/)).toBeTruthy();
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("backfill-skipped").textContent,
      ).toMatch(/5 already embedded/);
    });
  });

  it("post-run summary surfaces failures and recovered counts when non-zero", async () => {
    // Phase 3B F2: distinct counters for the three failure-modes.
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    mockedApi.backfillCount.mockResolvedValue(0);
    mockedApi.backfillStatus.mockResolvedValue({
      finished: true,
      cancelled: false,
      total: 100,
      completed: 95,
      failures: 3,
      recovered_failures: 2,
      skipped_already_embedded: 0,
      current_domain: null,
      started_at_ms: 0,
    });
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Last backfill: 95 indexed/)).toBeTruthy();
    });
    expect(screen.getByTestId("backfill-failures").textContent).toMatch(
      /3 failed/,
    );
    expect(screen.getByTestId("backfill-recovered").textContent).toMatch(
      /2 recovered after retry/,
    );
  });

  it("post-run summary omits failure + recovered chips on a clean happy-path run", async () => {
    // Happy path stays terse — no clutter when there's nothing to flag.
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    mockedApi.backfillCount.mockResolvedValue(0);
    mockedApi.backfillStatus.mockResolvedValue({
      finished: true,
      cancelled: false,
      total: 50,
      completed: 50,
      failures: 0,
      recovered_failures: 0,
      skipped_already_embedded: 0,
      current_domain: null,
      started_at_ms: 0,
    });
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByText(/Last backfill: 50 indexed/)).toBeTruthy();
    });
    expect(screen.queryByTestId("backfill-failures")).toBeNull();
    expect(screen.queryByTestId("backfill-recovered")).toBeNull();
    expect(screen.queryByTestId("backfill-skipped")).toBeNull();
  });

  it("failures chip carries error-tone class so attention is warranted", async () => {
    // Per AUDIT_ROW_UI_RESEARCH discipline: lost-data is the headline,
    // visually distinct from the informational counters.
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" } as ReadinessState);
    mockedApi.backfillCount.mockResolvedValue(0);
    mockedApi.backfillStatus.mockResolvedValue({
      finished: true,
      cancelled: false,
      total: 10,
      completed: 9,
      failures: 1,
      recovered_failures: 0,
      skipped_already_embedded: 0,
      current_domain: null,
      started_at_ms: 0,
    });
    render(<RetrievalTab refreshKey={0} />);
    await waitFor(() => {
      expect(screen.getByTestId("backfill-failures")).toBeTruthy();
    });
    const chip = screen.getByTestId("backfill-failures");
    // Visual emphasis: must use the err-tone Tailwind classes, not the
    // muted class the recovered/skipped counters share.
    expect(chip.className).toMatch(/text-aether-err/);
    expect(chip.className).not.toMatch(/text-aether-muted/);
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
