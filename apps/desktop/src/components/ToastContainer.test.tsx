// Branching tests for the backfill-done toast surface.
//
// Phase 3B F2 split the post-run toast into three branches that
// correspond to the three Phase 3B F1 counters:
//   - failures > 0  → warn-tone toast with re-run hint
//   - recovered_failures > 0 (no failures) → ok-tone toast that names
//     the transient recovery so the user understands it isn't silent
//   - clean run → existing terse ok-tone toast
//
// We assert the strings the user sees because they're the surface the
// quality standard #3 (don't lie to the user) applies to. Tone is
// asserted via the rendered className the Toast component picks per
// `TONE_CLASSES`.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";

import { ToastContainer } from "./ToastContainer";
import type { BackfillProgress } from "../lib/api";

vi.mock("../lib/api", () => ({
  embeddingsReadiness: vi.fn(),
  onBackfillDone: vi.fn(),
}));

import * as api from "../lib/api";

type DonePayload = { job_id: string } & BackfillProgress;

const mockedApi = api as unknown as {
  embeddingsReadiness: ReturnType<typeof vi.fn>;
  onBackfillDone: ReturnType<typeof vi.fn>;
};

/** Capture the callback registered with onBackfillDone so tests can
 * synthesise a `backfill:done` event without coupling to Tauri. */
function captureDoneCallback(): (payload: DonePayload) => void {
  let captured: ((payload: DonePayload) => void) | null = null;
  mockedApi.onBackfillDone.mockImplementation(
    async (cb: (payload: DonePayload) => void) => {
      captured = cb;
      return () => {};
    },
  );
  return (payload: DonePayload) => {
    if (!captured) throw new Error("onBackfillDone callback never registered");
    captured(payload);
  };
}

function donePayload(over: Partial<BackfillProgress>): DonePayload {
  return {
    job_id: "job-test",
    finished: true,
    cancelled: false,
    total: 0,
    completed: 0,
    failures: 0,
    recovered_failures: 0,
    skipped_already_embedded: 0,
    current_domain: null,
    started_at_ms: 0,
    ...over,
  };
}

beforeEach(() => {
  mockedApi.embeddingsReadiness.mockReset();
  mockedApi.embeddingsReadiness.mockResolvedValue({ kind: "ready" });
  mockedApi.onBackfillDone.mockReset();
});

describe("ToastContainer backfill-done branches", () => {
  it("emits an ok toast on a clean run with no failures or recoveries", async () => {
    const fire = captureDoneCallback();
    render(<ToastContainer />);
    await waitFor(() => {
      expect(mockedApi.onBackfillDone).toHaveBeenCalled();
    });
    act(() => {
      fire(donePayload({ total: 10, completed: 10 }));
    });
    const toast = await screen.findByText(
      /Backfill complete — 10 memories indexed\./,
    );
    // ok tone uses the aether-ok color token.
    expect(toast.closest("div")?.className).toMatch(/aether-ok/);
  });

  it("emits an ok toast naming the recovered transient errors", async () => {
    const fire = captureDoneCallback();
    render(<ToastContainer />);
    await waitFor(() => {
      expect(mockedApi.onBackfillDone).toHaveBeenCalled();
    });
    act(() => {
      fire(
        donePayload({
          total: 100,
          completed: 100,
          recovered_failures: 3,
        }),
      );
    });
    const toast = await screen.findByText(
      /Backfill complete — 100 indexed \(3 transient errors recovered\)\./,
    );
    expect(toast.closest("div")?.className).toMatch(/aether-ok/);
  });

  it("uses the singular noun when exactly one transient error recovered", async () => {
    const fire = captureDoneCallback();
    render(<ToastContainer />);
    await waitFor(() => {
      expect(mockedApi.onBackfillDone).toHaveBeenCalled();
    });
    act(() => {
      fire(
        donePayload({ total: 50, completed: 50, recovered_failures: 1 }),
      );
    });
    await screen.findByText(
      /Backfill complete — 50 indexed \(1 transient error recovered\)\./,
    );
  });

  it("emits a warn toast with a re-run hint when failures > 0", async () => {
    const fire = captureDoneCallback();
    render(<ToastContainer />);
    await waitFor(() => {
      expect(mockedApi.onBackfillDone).toHaveBeenCalled();
    });
    act(() => {
      fire(
        donePayload({
          total: 100,
          completed: 95,
          failures: 5,
          recovered_failures: 2,
        }),
      );
    });
    const toast = await screen.findByText(
      /Backfill complete — 95 indexed, 5 failed\. Re-run to retry\./,
    );
    // warn tone uses the aether-warn color token.
    expect(toast.closest("div")?.className).toMatch(/aether-warn/);
  });

  it("prefers the cancelled toast over failure / recovered branches", async () => {
    // Cancellation is the user's intent — it takes precedence over
    // any partial-run failure counters.
    const fire = captureDoneCallback();
    render(<ToastContainer />);
    await waitFor(() => {
      expect(mockedApi.onBackfillDone).toHaveBeenCalled();
    });
    act(() => {
      fire(
        donePayload({
          cancelled: true,
          total: 100,
          completed: 40,
          failures: 2,
          recovered_failures: 1,
        }),
      );
    });
    await screen.findByText(/Backfill cancelled at 40 of 100 memories\./);
    expect(
      screen.queryByText(/transient/),
    ).toBeNull();
    expect(screen.queryByText(/Re-run to retry/)).toBeNull();
  });
});
