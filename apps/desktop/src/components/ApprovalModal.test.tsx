// Wave 14 (T1.3 §5.3) — vitest coverage for the ApprovalModal radio
// surface. Locks the four-option fixed display order, the default
// selection, and the radio-id → UserChoice mapping. The wire-string
// regression is co-locked at the Rust layer in
// commands::tests::wave14_user_choice_wire_deserializes_from_snake_case_tags;
// these tests assert the renderer side of the same contract.

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ApprovalModal } from "./ApprovalModal";
import {
  APPROVAL_RADIO_OPTIONS,
  type ApprovalPayload,
  type UserChoice,
} from "../lib/types";

const PAYLOAD: ApprovalPayload = {
  ticket_id: "ticket-abc",
  capability: "files.edit",
  scope: "/tmp/aether-wave14.txt",
  reason: "approval_required",
  risk_hint: "Files-edit can mutate disk.",
  // Wave 15 — both gates open so the existing Wave 14 surface tests
  // observe all four radio options. Wave 15-specific gating tests
  // override these flags below.
  task_id_present: true,
  side_effecting: true,
};

function renderModal(
  onResolve = vi.fn(),
  working = false,
  payload: ApprovalPayload = PAYLOAD,
) {
  render(
    <ApprovalModal payload={payload} working={working} onResolve={onResolve} />,
  );
  return onResolve;
}

describe("ApprovalModal — Wave 14 radio surface", () => {
  it("renders the payload fields (capability / scope / reason / ticket)", () => {
    renderModal();
    expect(screen.getByText("files.edit")).toBeTruthy();
    expect(screen.getByText("/tmp/aether-wave14.txt")).toBeTruthy();
    expect(screen.getByText("approval_required")).toBeTruthy();
    expect(screen.getByText("ticket-abc")).toBeTruthy();
  });

  it("renders four radio options in the fixed design-§5.1 order", () => {
    renderModal();
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.value)).toEqual([
      "allow_once",
      "allow_task",
      "allow_session",
      "defer_draft",
    ]);
  });

  it("selects allow_once by default", () => {
    renderModal();
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const allowOnce = radios.find((r) => r.value === "allow_once");
    expect(allowOnce?.checked).toBe(true);
    // No other radio is checked.
    const others = radios.filter((r) => r.value !== "allow_once");
    expect(others.every((r) => !r.checked)).toBe(true);
  });

  it("emits UserChoice::Allow when Approve is clicked with the default radio", () => {
    const onResolve = renderModal();
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onResolve).toHaveBeenCalledTimes(1);
    expect(onResolve).toHaveBeenCalledWith({ kind: "allow" } satisfies UserChoice);
  });

  it.each(APPROVAL_RADIO_OPTIONS)(
    "maps radio %s to its UserChoice on Approve",
    ({ id, choice }) => {
      const onResolve = renderModal();
      // Click the radio we want, then submit Approve.
      const radio = screen
        .getAllByRole("radio")
        .find((r) => (r as HTMLInputElement).value === id);
      expect(radio).toBeTruthy();
      fireEvent.click(radio!);
      fireEvent.click(screen.getByRole("button", { name: /approve/i }));
      expect(onResolve).toHaveBeenCalledTimes(1);
      expect(onResolve).toHaveBeenCalledWith(choice);
    },
  );

  it("emits UserChoice::Deny when Decline is clicked, regardless of radio selection", () => {
    const onResolve = renderModal();
    // Pick a non-default radio just to prove Decline ignores the
    // radio selection (it is the safety-default escape).
    const sessionRadio = screen
      .getAllByRole("radio")
      .find((r) => (r as HTMLInputElement).value === "allow_session");
    fireEvent.click(sessionRadio!);
    fireEvent.click(screen.getByRole("button", { name: /decline/i }));
    expect(onResolve).toHaveBeenCalledTimes(1);
    expect(onResolve).toHaveBeenCalledWith({ kind: "deny" } satisfies UserChoice);
  });

  it("disables both buttons + the radio fieldset while working", () => {
    renderModal(vi.fn(), /* working = */ true);
    const approveBtn = screen.getByRole("button", { name: /working/i });
    const declineBtn = screen.getByRole("button", { name: /decline/i });
    expect((approveBtn as HTMLButtonElement).disabled).toBe(true);
    expect((declineBtn as HTMLButtonElement).disabled).toBe(true);
    // Radios live inside a disabled fieldset — the browser/JSDOM
    // disables every nested form control automatically.
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.every((r) => r.disabled)).toBe(true);
  });

  it("renders the dialog with aria-modal + a labelled title", () => {
    renderModal();
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("approval-title");
    expect(screen.getByText(/permission to continue/i)).toBeTruthy();
  });
});

describe("ApprovalModal — Wave 15 affordance gating", () => {
  function payloadWith(
    task_id_present: boolean,
    side_effecting: boolean,
  ): ApprovalPayload {
    return { ...PAYLOAD, task_id_present, side_effecting };
  }

  it("hides allow_task when task_id_present is false", () => {
    renderModal(vi.fn(), false, payloadWith(false, true));
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const ids = radios.map((r) => r.value);
    expect(ids).toEqual(["allow_once", "allow_session", "defer_draft"]);
  });

  it("hides defer_draft when side_effecting is false", () => {
    renderModal(vi.fn(), false, payloadWith(true, false));
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const ids = radios.map((r) => r.value);
    expect(ids).toEqual(["allow_once", "allow_task", "allow_session"]);
  });

  it("hides both allow_task and defer_draft when both flags are false", () => {
    renderModal(vi.fn(), false, payloadWith(false, false));
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const ids = radios.map((r) => r.value);
    expect(ids).toEqual(["allow_once", "allow_session"]);
  });

  it("renders all four options when both flags are true", () => {
    renderModal(vi.fn(), false, payloadWith(true, true));
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.value)).toEqual([
      "allow_once",
      "allow_task",
      "allow_session",
      "defer_draft",
    ]);
  });

  it("keeps allow_once selected by default even when other options are gated out", () => {
    renderModal(vi.fn(), false, payloadWith(false, false));
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const allowOnce = radios.find((r) => r.value === "allow_once");
    expect(allowOnce?.checked).toBe(true);
  });

  it("Approve emits UserChoice::Allow on a fully-gated payload (only allow_once visible)", () => {
    const onResolve = vi.fn();
    renderModal(onResolve, false, payloadWith(false, false));
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onResolve).toHaveBeenCalledTimes(1);
    expect(onResolve).toHaveBeenCalledWith({ kind: "allow" } satisfies UserChoice);
  });
});
