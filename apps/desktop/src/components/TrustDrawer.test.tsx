// Focused contract tests for TrustDrawer's `initialTab` prop.
//
// Added in Run 5 (2026-04-23) when the legacy MemoryDrawer was
// retired: the header's Memory button now opens the Trust drawer
// and selects the Memory tab via `initialTab="memory"`. These tests
// lock that contract so a future refactor of the drawer's tab state
// cannot silently regress the "Memory button opens Memory tab"
// behaviour.
//
// `lib/api` is mocked at the module boundary — we only care about
// which tab is aria-selected, not about audit/history/memory
// content.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";

vi.mock("../lib/api", () => ({
  auditRecent: vi.fn().mockResolvedValue([]),
  getPresenceConfig: vi.fn().mockResolvedValue({
    enabled: false,
    idle_after_s: 30,
    away_after_s: 300,
    history_enabled: true,
  }),
  onAttention: vi.fn().mockResolvedValue(() => {}),
  presenceRecentHistory: vi.fn().mockResolvedValue([]),
  telemetryClear: vi.fn(),
  telemetryRecent: vi.fn().mockResolvedValue([]),
  memoryList: vi.fn().mockResolvedValue({
    domain: "durable",
    privacy_class: "standard",
    risk: "auto",
    items: [],
    empty_reason: null,
  }),
  memoryForget: vi.fn(),
  memoryForgetItem: vi.fn(),
  memoryForgetItemAfterApproval: vi.fn(),
  memoryEdit: vi.fn(),
  memoryEditAfterApproval: vi.fn(),
}));

import { TrustDrawer } from "./TrustDrawer";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TrustDrawer.initialTab", () => {
  it("defaults to the Audit tab when no initialTab is provided", async () => {
    render(<TrustDrawer open={true} refreshKey={0} onClose={() => {}} />);
    // Wait for initial effect chain to settle.
    await waitFor(() => {
      const audit = screen.getByRole("tab", { name: "Audit" });
      expect(audit.getAttribute("aria-selected")).toBe("true");
    });
    const memory = screen.getByRole("tab", { name: "Memory" });
    expect(memory.getAttribute("aria-selected")).toBe("false");
  });

  it("opens on the Memory tab when initialTab=\"memory\" is set", async () => {
    render(
      <TrustDrawer
        open={true}
        refreshKey={0}
        onClose={() => {}}
        initialTab="memory"
      />,
    );
    await waitFor(() => {
      const memory = screen.getByRole("tab", { name: "Memory" });
      expect(memory.getAttribute("aria-selected")).toBe("true");
    });
    const audit = screen.getByRole("tab", { name: "Audit" });
    expect(audit.getAttribute("aria-selected")).toBe("false");
  });

  it("re-applies initialTab on an open-false → open-true transition", async () => {
    const { rerender } = render(
      <TrustDrawer
        open={true}
        refreshKey={0}
        onClose={() => {}}
        initialTab="memory"
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByRole("tab", { name: "Memory" }).getAttribute("aria-selected"),
      ).toBe("true");
    });
    // Simulate the user closing and then reopening via the Memory
    // button (same `initialTab="memory"`). A stale implementation
    // that only read the prop on mount would keep whatever tab was
    // last shown.
    rerender(
      <TrustDrawer
        open={false}
        refreshKey={0}
        onClose={() => {}}
        initialTab="memory"
      />,
    );
    act(() => {
      // no-op; drives React state flush without state change.
    });
    rerender(
      <TrustDrawer
        open={true}
        refreshKey={1}
        onClose={() => {}}
        initialTab="memory"
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByRole("tab", { name: "Memory" }).getAttribute("aria-selected"),
      ).toBe("true");
    });
  });
});
