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

// ---------------------------------------------------------------------------
// ADR-0009 — version-aware AuditRow rendering.
//
// Locks the contract that:
//   - v1 rows show a "pre-ADR-0009" badge and DO NOT render the
//     user-utterance headline (because v1 had no field to render).
//   - v2 rows render the user's text prominently, demote
//     capability/scope to a secondary line, and surface the
//     retrieval-block summary in a collapsed details/summary.
//   - The "model_input_utterance" string itself is NOT rendered
//     (Open Item #3, deferred per DECISIONS_LOG.md D-001).
// ---------------------------------------------------------------------------

import {
  AUDIT_SCHEMA_VERSION_V1,
  AUDIT_SCHEMA_VERSION_V2,
  AuditRow,
} from "./TrustDrawer";
import type { TrustAuditRow } from "../lib/types";

function v1Row(overrides: Partial<TrustAuditRow> = {}): TrustAuditRow {
  return {
    audit_id: "row-v1",
    decision: "allow",
    capability: "files.read",
    scope: "/tmp/x",
    change_id: "c-v1",
    at_mono_ns: 1_000,
    at_epoch_s: 1_700_000_000,
    schema_version: AUDIT_SCHEMA_VERSION_V1,
    ...overrides,
  };
}

function v2Row(overrides: Partial<TrustAuditRow> = {}): TrustAuditRow {
  return {
    audit_id: "row-v2",
    decision: "allow",
    capability: "conversation",
    scope: "session",
    change_id: "c-v2",
    at_mono_ns: 2_000,
    at_epoch_s: 1_700_000_500,
    schema_version: AUDIT_SCHEMA_VERSION_V2,
    original_utterance: "what about sourdough?",
    retrieval_provenance: {
      block_present: true,
      hits: [
        { memory_id: "mem-12", domain: "durable", score: 0.81 },
        { memory_id: "mem-44", domain: "facts", score: 0.72 },
      ],
    },
    ...overrides,
  };
}

describe("AuditRow — ADR-0009 version-aware rendering", () => {
  it("v1 row shows the pre-ADR-0009 badge and no user-utterance headline", () => {
    render(<AuditRow row={v1Row()} />);
    expect(screen.getByTestId("schema-v1-badge")).toBeTruthy();
    expect(screen.queryByTestId("audit-user-utterance")).toBeNull();
    // capability text remains the primary line on v1.
    expect(screen.getByText("files.read")).toBeTruthy();
  });

  it("v2 row hoists the user's text and hides the v1 badge", () => {
    render(<AuditRow row={v2Row()} />);
    const utter = screen.getByTestId("audit-user-utterance");
    expect(utter.textContent).toContain("what about sourdough?");
    expect(screen.queryByTestId("schema-v1-badge")).toBeNull();
  });

  it("v2 row exposes a model-saw disclosure summarizing retrieval hit count + domains", () => {
    render(<AuditRow row={v2Row()} />);
    const details = screen.getByTestId("audit-model-saw");
    // Summary text is the visible top-line of <details>.
    expect(details.textContent).toContain("2 memories");
    expect(details.textContent).toContain("durable");
    expect(details.textContent).toContain("facts");
  });

  it("v2 row with empty retrieval reports 'nothing matched' honestly without a misleading disclosure (Phase 6 Bug 5.3)", () => {
    render(
      <AuditRow
        row={v2Row({
          retrieval_provenance: { block_present: false, hits: [] },
        })}
      />,
    );
    // The empty-retrieval message is rendered as inline text, NOT as
    // a <details>/<summary> chevron — clicking a chevron that
    // reveals nothing is the exact misleading affordance Phase 6
    // flagged. AUDIT_ROW_UI_RESEARCH §2.3 anticipated this.
    const empty = screen.getByTestId("audit-model-saw-empty");
    expect(empty.textContent).toContain("nothing matched");
    expect(empty.tagName.toLowerCase()).toBe("div");
    expect(screen.queryByTestId("audit-model-saw")).toBeNull();
  });

  it("v2 row with block_present:false does NOT render the disclosure chevron (Phase 6 Bug 5.3)", () => {
    render(
      <AuditRow
        row={v2Row({
          retrieval_provenance: { block_present: false, hits: [] },
        })}
      />,
    );
    expect(screen.queryByTestId("audit-model-saw")).toBeNull();
    expect(screen.getByTestId("audit-model-saw-empty")).toBeTruthy();
  });

  it("v2 row with no retrieval_provenance omits the model-saw disclosure entirely", () => {
    render(
      <AuditRow row={v2Row({ retrieval_provenance: undefined })} />,
    );
    expect(screen.queryByTestId("audit-model-saw")).toBeNull();
  });

  it("v2 row never renders the augmented model-input string itself", () => {
    // ADR-0009 Open Item #3 (deferred). The rendered DOM must not
    // contain the synthetic "Relevant context (retrieval):" prefix
    // that the prompt builder uses, because the row only carries
    // `original_utterance`, not `model_input_utterance`.
    const { container } = render(<AuditRow row={v2Row()} />);
    expect(container.textContent).not.toContain(
      "Relevant context (retrieval):",
    );
  });
});

// ---------------------------------------------------------------------------
// Phase 6 UX audit Bug 5.2 — focus trap.
//
// The drawer is now a modal (role="dialog" + aria-modal). When it
// opens it must:
//   - blur whatever previously held focus, so stray keystrokes do
//     not accumulate in the chat input behind it,
//   - swallow keystrokes whose target is outside the drawer subtree
//     (modifier-only shortcuts pass through),
//   - restore focus to the previously-focused element on close.
// ---------------------------------------------------------------------------

describe("TrustDrawer — Phase 6 Bug 5.2 focus trap", () => {
  it("blurs the previously-focused chat input on open and swallows stray keystrokes", async () => {
    // Stand-in chat input outside the drawer.
    const chatInput = document.createElement("textarea");
    chatInput.setAttribute("data-testid", "fake-chat-input");
    document.body.appendChild(chatInput);
    chatInput.focus();
    expect(document.activeElement).toBe(chatInput);

    const { unmount } = render(
      <TrustDrawer open={true} refreshKey={0} onClose={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("trust-drawer-root")).toBeTruthy();
    });

    // After the open effect runs, focus must have left the chat
    // input — otherwise keystrokes typed before the user clicks
    // anywhere will land in the composer.
    expect(document.activeElement).not.toBe(chatInput);

    // Simulate a stray keystroke whose target is the chat input.
    // The drawer's capture-phase keydown listener should call
    // preventDefault on it, signalling that the keystroke would not
    // produce text in the composer in a real browser.
    const evt = new KeyboardEvent("keydown", {
      key: "a",
      bubbles: true,
      cancelable: true,
    });
    chatInput.dispatchEvent(evt);
    expect(evt.defaultPrevented).toBe(true);

    unmount();
    document.body.removeChild(chatInput);
  });

  it("uses role=dialog + aria-modal so assistive tech treats it as a modal surface", async () => {
    render(<TrustDrawer open={true} refreshKey={0} onClose={() => {}} />);
    await waitFor(() => {
      const root = screen.getByTestId("trust-drawer-root");
      expect(root.getAttribute("role")).toBe("dialog");
      expect(root.getAttribute("aria-modal")).toBe("true");
    });
  });
});
