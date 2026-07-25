import { expect, test } from "@playwright/test";

import {
  installTauriMock,
  readCalls,
  readResolveChoice,
  type MockApprovalPayload,
} from "./tauri-mock";

/**
 * Wave 19 — Doctrine §8 used-as-user verification of the Wave 14/15
 * approval modal. Each test drives the real frontend in Chromium with
 * the Tauri IPC mocked, then asserts behaviour the jsdom unit suite
 * cannot reach: real visibility, real radio semantics, real focus, and
 * the live App.tsx path `submit_turn` → modal → `resolve_approval`.
 */

const FULL_PAYLOAD: MockApprovalPayload = {
  ticket_id: "tkt-001",
  capability: "files.write",
  scope: "/tmp/x",
  reason: "Persist the note you asked me to save.",
  risk_hint: "This writes a file to disk.",
  task_id_present: true,
  side_effecting: true,
};

/** Submit a turn from the chat input and wait for the gate to raise
 * the modal. Returns the modal locator. */
async function raiseModal(page: import("@playwright/test").Page) {
  // Placeholder is personalised ("Message <persona>…"), so target the
  // single chat textbox by role rather than by placeholder text.
  const input = page.getByRole("textbox");
  await expect(input).toBeVisible();
  await input.fill("write /tmp/x");
  await input.press("Enter");
  const modal = page.getByRole("dialog", { name: /permission/i });
  await expect(modal).toBeVisible();
  return modal;
}

test.describe("approval modal — used-as-user", () => {
  test("raises the modal and renders the payload fields", async ({ page }) => {
    await installTauriMock(page, { approval: FULL_PAYLOAD });
    await page.goto("/");
    const modal = await raiseModal(page);

    await expect(modal.getByText("files.write")).toBeVisible();
    await expect(modal.getByText("/tmp/x")).toBeVisible();
    await expect(
      modal.getByText("Persist the note you asked me to save."),
    ).toBeVisible();
    await expect(modal.getByText("tkt-001")).toBeVisible();
    await expect(modal.getByText(/This writes a file to disk\./)).toBeVisible();
  });

  test("shows all four scope options when task + side-effecting", async ({
    page,
  }) => {
    await installTauriMock(page, { approval: FULL_PAYLOAD });
    await page.goto("/");
    const modal = await raiseModal(page);

    await expect(modal.getByRole("radio", { name: "Allow once" })).toBeVisible();
    await expect(
      modal.getByRole("radio", { name: "Allow for this task" }),
    ).toBeVisible();
    await expect(
      modal.getByRole("radio", { name: "Allow for this session" }),
    ).toBeVisible();
    await expect(
      modal.getByRole("radio", { name: /Draft only/ }),
    ).toBeVisible();

    // "Allow once" is the default selection.
    await expect(
      modal.getByRole("radio", { name: "Allow once" }),
    ).toBeChecked();
  });

  test("Approve with a chosen scope sends the matching UserChoice", async ({
    page,
  }) => {
    await installTauriMock(page, { approval: FULL_PAYLOAD });
    await page.goto("/");
    const modal = await raiseModal(page);

    await modal.getByRole("radio", { name: "Allow for this session" }).check();
    await modal.getByRole("button", { name: "Approve" }).click();

    // Modal closes after resolution.
    await expect(modal).toBeHidden();

    const choice = await readResolveChoice(page);
    expect(choice).toMatchObject({
      ticketId: "tkt-001",
      userChoice: { kind: "allow_session" },
    });
  });

  test("Approve with the default scope sends allow", async ({ page }) => {
    await installTauriMock(page, { approval: FULL_PAYLOAD });
    await page.goto("/");
    const modal = await raiseModal(page);

    await modal.getByRole("button", { name: "Approve" }).click();
    await expect(modal).toBeHidden();

    const choice = await readResolveChoice(page);
    expect(choice).toMatchObject({ userChoice: { kind: "allow" } });
  });

  test("Decline sends deny and closes the modal", async ({ page }) => {
    await installTauriMock(page, { approval: FULL_PAYLOAD });
    await page.goto("/");
    const modal = await raiseModal(page);

    await modal.getByRole("button", { name: "Decline" }).click();
    await expect(modal).toBeHidden();

    const choice = await readResolveChoice(page);
    expect(choice).toMatchObject({ userChoice: { kind: "deny" } });
  });

  test("hides allow_task when there is no task lineage", async ({ page }) => {
    await installTauriMock(page, {
      approval: { ...FULL_PAYLOAD, task_id_present: false },
    });
    await page.goto("/");
    const modal = await raiseModal(page);

    await expect(
      modal.getByRole("radio", { name: "Allow for this task" }),
    ).toHaveCount(0);
    // The other options remain.
    await expect(modal.getByRole("radio", { name: "Allow once" })).toBeVisible();
    await expect(
      modal.getByRole("radio", { name: /Draft only/ }),
    ).toBeVisible();
  });

  test("hides defer_draft for read-only (non-side-effecting) capabilities", async ({
    page,
  }) => {
    await installTauriMock(page, {
      approval: {
        ...FULL_PAYLOAD,
        capability: "files.read",
        side_effecting: false,
      },
    });
    await page.goto("/");
    const modal = await raiseModal(page);

    await expect(
      modal.getByRole("radio", { name: /Draft only/ }),
    ).toHaveCount(0);
    await expect(modal.getByRole("radio", { name: "Allow once" })).toBeVisible();
  });

  test("modal is an accessible, focus-trappable dialog (real DOM)", async ({
    page,
  }) => {
    await installTauriMock(page, { approval: FULL_PAYLOAD });
    await page.goto("/");
    const modal = await raiseModal(page);

    await expect(modal).toHaveAttribute("aria-modal", "true");
    await expect(modal.getByRole("radiogroup")).toBeVisible();

    // Keyboard: a radio can be focused and selected without the mouse.
    const sessionRadio = modal.getByRole("radio", {
      name: "Allow for this session",
    });
    await sessionRadio.focus();
    await expect(sessionRadio).toBeFocused();
    await sessionRadio.press("Space");
    await expect(sessionRadio).toBeChecked();

    // Doctrine §8 artifact: capture the rendered modal.
    await modal.screenshot({ path: "e2e/.artifacts/approval-modal.png" });
  });

  test("a plain (no-approval) turn never raises the modal", async ({ page }) => {
    await installTauriMock(page, {}); // submit_turn returns completed
    await page.goto("/");
    const input = page.getByRole("textbox");
    await expect(input).toBeVisible();
    await input.fill("hello");
    await input.press("Enter");

    await expect(page.getByRole("dialog")).toHaveCount(0);
    const calls = await readCalls(page);
    expect(calls.some((c) => c.cmd === "submit_turn")).toBe(true);
    expect(calls.some((c) => c.cmd === "resolve_approval")).toBe(false);
  });
});
