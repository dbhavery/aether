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
});
