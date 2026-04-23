// Component tests for MemoryTab — Memory V2 step 4 Trust-drawer surface.
//
// The `lib/api` module is mocked so every test drives the tab through
// the TS client surface. Assertions stay close to user-visible text and
// roles; implementation details (CSS classes, internal state shape)
// are not the contract under test.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";

import {
  classifyEdit,
  classifyForget,
  MemoryTab,
  previewForSummary,
} from "./MemoryTab";
import type { MemoryListPayload } from "../lib/types";

vi.mock("../lib/api", () => ({
  memoryList: vi.fn(),
  memoryForget: vi.fn(),
  memoryForgetItem: vi.fn(),
  memoryForgetItemAfterApproval: vi.fn(),
  memoryEdit: vi.fn(),
  memoryEditAfterApproval: vi.fn(),
}));

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  memoryList: ReturnType<typeof vi.fn>;
  memoryForget: ReturnType<typeof vi.fn>;
  memoryForgetItem: ReturnType<typeof vi.fn>;
  memoryForgetItemAfterApproval: ReturnType<typeof vi.fn>;
  memoryEdit: ReturnType<typeof vi.fn>;
  memoryEditAfterApproval: ReturnType<typeof vi.fn>;
};

function lane(
  domain: MemoryListPayload["domain"],
  overrides: Partial<MemoryListPayload> = {},
): MemoryListPayload {
  const privacy_class =
    domain === "facts" || domain === "artifacts"
      ? "user_sensitive"
      : "standard";
  return {
    domain,
    privacy_class,
    risk: privacy_class === "user_sensitive" ? "ask" : "auto",
    items: [],
    empty_reason: null,
    ...overrides,
  };
}

function sessionLaneWithOne(content = "hello world") {
  return lane("session", {
    empty_reason: null,
    items: [
      {
        memory_id: "mem-aether-desktop-1",
        sequence: 1,
        timestamp_ms: 1_717_000_000_000,
        role: "user",
        content,
        source: "conversation",
      },
    ],
  });
}

function stubAllDomainsWith(sessionPayload: MemoryListPayload) {
  mockedApi.memoryList.mockImplementation(async (domain: string) => {
    if (domain === "session") return sessionPayload;
    return lane(domain as MemoryListPayload["domain"], {
      empty_reason: "Storage for this domain arrives with Memory V2 step 5.",
    });
  });
}

beforeEach(() => {
  for (const k of Object.keys(mockedApi) as (keyof typeof mockedApi)[]) {
    mockedApi[k].mockReset();
  }
});

describe("classifyForget / classifyEdit", () => {
  it("turns allowed into refresh", () => {
    expect(
      classifyForget({ kind: "allowed", removed_count: 1, audit_id: "a" }),
    ).toBe("refresh");
    expect(
      classifyEdit({
        kind: "allowed",
        memory_id: "mem-s-1",
        audit_id: "a",
      }),
    ).toBe("refresh");
  });

  it("surfaces denied with a readable error string", () => {
    const got = classifyForget({ kind: "denied", reason: "config_deny" });
    expect(got).toEqual({ error: "Forget denied: config_deny" });
    const gotE = classifyEdit({ kind: "denied", reason: "l5_deny" });
    expect(gotE).toEqual({ error: "Edit denied: l5_deny" });
  });

  it("marks requires_approval as its own branch", () => {
    expect(classifyForget({ kind: "requires_approval" })).toBe(
      "requires_approval",
    );
  });

  it("maps not_found to a silent-refresh hint", () => {
    expect(classifyForget({ kind: "not_found" })).toBe("already_gone");
    expect(classifyEdit({ kind: "not_found" })).toBe("already_gone");
  });
});

describe("previewForSummary", () => {
  it("keeps short content as-is", () => {
    expect(previewForSummary("short and sweet")).toBe("short and sweet");
  });

  it("collapses whitespace and truncates in the middle for long content", () => {
    const long =
      "This is quite a long content line that\t\thas irregular whitespace and keeps going and going until it must be truncated.";
    const summary = previewForSummary(long);
    expect(summary.length).toBeLessThan(long.length);
    expect(summary).toMatch(/…/);
    // Start and end pieces come from the original.
    expect(summary.startsWith("This is quite a long content")).toBe(true);
    expect(summary.endsWith("must be truncated.")).toBe(true);
  });
});

describe("MemoryTab rendering", () => {
  it("renders all six domain lanes with empty-state copy for non-session domains", async () => {
    stubAllDomainsWith(lane("session"));
    render(<MemoryTab open refreshKey={0} />);

    for (const d of [
      "session",
      "durable",
      "facts",
      "projects",
      "preferences",
      "artifacts",
    ]) {
      expect(
        await screen.findByRole("region", { name: `Memory domain ${d}` }),
      ).toBeTruthy();
    }
    // Five non-session lanes should carry the step-5 empty reason.
    const stepFiveBlurbs = await screen.findAllByText(
      /Memory V2 step 5/,
    );
    expect(stepFiveBlurbs.length).toBe(5);
  });

  it("shows the user-sensitive pill on Facts and Artifacts only", async () => {
    stubAllDomainsWith(lane("session"));
    render(<MemoryTab open refreshKey={0} />);
    const sensitivePills = await screen.findAllByText("user-sensitive");
    expect(sensitivePills.length).toBe(2);
  });

  it("renders an item row in the session lane when the payload has one", async () => {
    stubAllDomainsWith(sessionLaneWithOne("pin this line"));
    render(<MemoryTab open refreshKey={0} />);
    expect(await screen.findByText("pin this line")).toBeTruthy();
    expect(
      await screen.findByRole("article", {
        name: "Memory item mem-aether-desktop-1",
      }),
    ).toBeTruthy();
  });

  it("skips all fetches when the drawer is closed", () => {
    render(<MemoryTab open={false} refreshKey={0} />);
    expect(mockedApi.memoryList).not.toHaveBeenCalled();
  });
});

describe("MemoryTab forget flow", () => {
  it("calls memoryForgetItem on the per-row Forget button and refreshes", async () => {
    stubAllDomainsWith(sessionLaneWithOne());
    mockedApi.memoryForgetItem.mockResolvedValue({
      kind: "allowed",
      removed_count: 1,
      audit_id: "audit-1",
    });

    render(<MemoryTab open refreshKey={0} />);

    const sessionLane = await screen.findByRole("region", {
      name: "Memory domain session",
    });
    const forget = within(sessionLane).getByRole("button", { name: "Forget" });
    fireEvent.click(forget);

    await waitFor(() => {
      expect(mockedApi.memoryForgetItem).toHaveBeenCalledWith(
        "session",
        "mem-aether-desktop-1",
      );
    });
    // Refresh issues a second batch of memoryList calls, one per domain.
    await waitFor(() => {
      expect(mockedApi.memoryList).toHaveBeenCalledTimes(12); // 6 initial + 6 refresh
    });
  });

  it("opens the confirmation dialog when the backend returns requires_approval", async () => {
    stubAllDomainsWith(sessionLaneWithOne("secret fact"));
    mockedApi.memoryForgetItem.mockResolvedValue({ kind: "requires_approval" });
    mockedApi.memoryForgetItemAfterApproval.mockResolvedValue({
      kind: "allowed",
      removed_count: 1,
      audit_id: "audit-2",
    });

    render(<MemoryTab open refreshKey={0} />);

    const sessionLane = await screen.findByRole("region", {
      name: "Memory domain session",
    });
    fireEvent.click(within(sessionLane).getByRole("button", { name: "Forget" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Forget this item?")).toBeTruthy();
    expect(within(dialog).getByText("secret fact")).toBeTruthy();

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Approve once" }),
    );

    await waitFor(() => {
      expect(mockedApi.memoryForgetItemAfterApproval).toHaveBeenCalledWith(
        "session",
        "mem-aether-desktop-1",
      );
    });
  });

  it("surfaces a readable error string when forget is denied", async () => {
    stubAllDomainsWith(sessionLaneWithOne());
    mockedApi.memoryForgetItem.mockResolvedValue({
      kind: "denied",
      reason: "config_deny",
    });

    render(<MemoryTab open refreshKey={0} />);

    const sessionLane = await screen.findByRole("region", {
      name: "Memory domain session",
    });
    fireEvent.click(within(sessionLane).getByRole("button", { name: "Forget" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/Forget denied: config_deny/);
  });
});

describe("MemoryTab edit flow", () => {
  it("opens an edit textarea and saves the new content", async () => {
    stubAllDomainsWith(sessionLaneWithOne("v1"));
    mockedApi.memoryEdit.mockResolvedValue({
      kind: "allowed",
      memory_id: "mem-aether-desktop-1",
      audit_id: "audit-3",
    });

    render(<MemoryTab open refreshKey={0} />);

    const sessionLane = await screen.findByRole("region", {
      name: "Memory domain session",
    });
    fireEvent.click(within(sessionLane).getByRole("button", { name: "Edit" }));

    const textarea = await screen.findByLabelText("Edit memory content");
    fireEvent.change(textarea, { target: { value: "v2" } });
    fireEvent.click(within(sessionLane).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(mockedApi.memoryEdit).toHaveBeenCalledWith(
        "session",
        "mem-aether-desktop-1",
        "v2",
      );
    });
  });

  it("routes edit through the confirmation dialog on Ask domains", async () => {
    stubAllDomainsWith(sessionLaneWithOne("v1"));
    mockedApi.memoryEdit.mockResolvedValue({ kind: "requires_approval" });
    mockedApi.memoryEditAfterApproval.mockResolvedValue({
      kind: "allowed",
      memory_id: "mem-aether-desktop-1",
      audit_id: "audit-4",
    });

    render(<MemoryTab open refreshKey={0} />);

    const sessionLane = await screen.findByRole("region", {
      name: "Memory domain session",
    });
    fireEvent.click(within(sessionLane).getByRole("button", { name: "Edit" }));
    const textarea = await screen.findByLabelText("Edit memory content");
    fireEvent.change(textarea, { target: { value: "v2" } });
    fireEvent.click(within(sessionLane).getByRole("button", { name: "Save" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Save this edit?")).toBeTruthy();
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Approve once" }),
    );

    await waitFor(() => {
      expect(mockedApi.memoryEditAfterApproval).toHaveBeenCalledWith(
        "session",
        "mem-aether-desktop-1",
        "v2",
      );
    });
  });
});

describe("MemoryTab forget-all flow", () => {
  it("wires the lane Forget-all button to memoryForget", async () => {
    stubAllDomainsWith(sessionLaneWithOne());
    mockedApi.memoryForget.mockResolvedValue({
      kind: "allowed",
      removed_count: 1,
      audit_id: "audit-5",
    });

    render(<MemoryTab open refreshKey={0} />);

    const sessionLane = await screen.findByRole("region", {
      name: "Memory domain session",
    });
    fireEvent.click(
      within(sessionLane).getByRole("button", { name: "Forget all" }),
    );

    await waitFor(() => {
      expect(mockedApi.memoryForget).toHaveBeenCalledWith("session");
    });
  });
});
