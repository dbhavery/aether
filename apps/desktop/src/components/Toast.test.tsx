// Smoke tests for Toast + ToastContainer (ADR-0007 D6 surface).

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";

import { Toast } from "./Toast";
import { ToastContainer } from "./ToastContainer";

vi.mock("../lib/api", () => ({
  embeddingsReadiness: vi.fn(),
  onBackfillDone: vi.fn(),
}));

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  embeddingsReadiness: ReturnType<typeof vi.fn>;
  onBackfillDone: ReturnType<typeof vi.fn>;
};

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the message and dismisses after duration", async () => {
    const onDismiss = vi.fn();
    render(
      <Toast id="t1" message="hello world" tone="info" durationMs={1000} onDismiss={onDismiss} />,
    );
    expect(screen.getByText("hello world")).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(1200);
    });
    expect(onDismiss).toHaveBeenCalledWith("t1");
  });

  it("applies the warn tone color class", () => {
    const { container } = render(
      <Toast id="t1" message="careful" tone="warn" onDismiss={() => {}} />,
    );
    const toastDiv = container.querySelector("[role='status']");
    expect(toastDiv?.className).toContain("text-aether-warn");
  });
});

describe("ToastContainer", () => {
  beforeEach(() => {
    vi.useRealTimers();
    mockedApi.embeddingsReadiness.mockReset();
    mockedApi.onBackfillDone.mockReset();
    mockedApi.onBackfillDone.mockResolvedValue(() => {});
  });

  it("renders nothing when no transitions have occurred", async () => {
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" });
    const { container } = render(<ToastContainer />);
    await waitFor(() => expect(mockedApi.embeddingsReadiness).toHaveBeenCalled());
    // No transitions yet => no toast.
    expect(container.querySelector("[role='status']")).toBeNull();
  });

  it("ignores readiness changes that go through 'unknown'", async () => {
    // Initial poll returns unknown; subsequent returns ready. Transition
    // unknown -> ready is intentionally silent (intentional state, not a
    // surface-worthy event).
    mockedApi.embeddingsReadiness
      .mockResolvedValueOnce({ kind: "unknown" })
      .mockResolvedValue({ kind: "ready" });
    const { container } = render(<ToastContainer />);
    await waitFor(() =>
      expect(mockedApi.embeddingsReadiness.mock.calls.length).toBeGreaterThanOrEqual(1),
    );
    expect(container.querySelector("[role='status']")).toBeNull();
  });

  it("emits a backfill-done toast when the event fires with completed > 0", async () => {
    let firedCb: ((p: any) => void) | null = null;
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" });
    mockedApi.onBackfillDone.mockImplementation(async (cb) => {
      firedCb = cb;
      return () => {};
    });

    render(<ToastContainer />);
    await waitFor(() => expect(firedCb).not.toBeNull());

    // Simulate a backfill done event with completed > 0.
    act(() => {
      firedCb!({
        job_id: "job-1",
        finished: true,
        cancelled: false,
        total: 12,
        completed: 12,
        failures: 0,
        current_domain: null,
        started_at_ms: 1,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/Backfill complete — 12 memories indexed/)).toBeTruthy();
    });
  });

  it("emits a backfill-done warn toast when the event fires with failures > 0", async () => {
    let firedCb: ((p: any) => void) | null = null;
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" });
    mockedApi.onBackfillDone.mockImplementation(async (cb) => {
      firedCb = cb;
      return () => {};
    });

    render(<ToastContainer />);
    await waitFor(() => expect(firedCb).not.toBeNull());

    act(() => {
      firedCb!({
        job_id: "job-2",
        finished: true,
        cancelled: false,
        total: 10,
        completed: 8,
        failures: 2,
        current_domain: null,
        started_at_ms: 1,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/Backfill complete — 8 indexed, 2 failed/)).toBeTruthy();
    });
  });

  it("emits an info toast when backfill is cancelled mid-run", async () => {
    let firedCb: ((p: any) => void) | null = null;
    mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" });
    mockedApi.onBackfillDone.mockImplementation(async (cb) => {
      firedCb = cb;
      return () => {};
    });

    render(<ToastContainer />);
    await waitFor(() => expect(firedCb).not.toBeNull());

    act(() => {
      firedCb!({
        job_id: "job-3",
        finished: true,
        cancelled: true,
        total: 20,
        completed: 5,
        failures: 0,
        current_domain: null,
        started_at_ms: 1,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/Backfill cancelled at 5 of 20 memories/)).toBeTruthy();
    });
  });
});
