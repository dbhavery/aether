import { expect, test } from "@playwright/test";

import { installTauriMock, readCalls } from "./tauri-mock";

/**
 * T2.4 — Doctrine §8 used-as-user verification of the header persona
 * picker. Confirms the picker surfaces only when >1 persona is
 * installed, and that switching persona propagates the new identity
 * across the UI (header name + personalised chat placeholder + the
 * control's own value) and carries the right id over IPC.
 */

const TWO_PERSONAS = [
  { id: "aurora", name: "Aurora", stance: "warm" },
  { id: "nova", name: "Nova", stance: "direct" },
];

test.describe("persona picker — used-as-user (T2.4)", () => {
  test("surfaces the switcher and the active identity when >1 installed", async ({
    page,
  }) => {
    await installTauriMock(page, { personas: TWO_PERSONAS });
    await page.goto("/");

    const input = page.getByRole("textbox");
    await expect(input).toBeVisible();

    const select = page.getByRole("combobox", { name: "Persona" });
    await expect(select).toBeVisible();
    await expect(select).toHaveValue("aurora");
    // Chat input placeholder is personalised to the active persona.
    await expect(input).toHaveAttribute("placeholder", /Aurora/);
  });

  test("switching persona propagates the new identity across the UI", async ({
    page,
  }) => {
    await installTauriMock(page, { personas: TWO_PERSONAS });
    await page.goto("/");

    const select = page.getByRole("combobox", { name: "Persona" });
    await expect(select).toBeVisible();
    await expect(select).toHaveValue("aurora");

    await select.selectOption("nova");

    // Control reflects the switch, and the chat placeholder re-renders
    // with the new persona's name — the user-visible identity change.
    await expect(select).toHaveValue("nova");
    await expect(page.getByRole("textbox")).toHaveAttribute(
      "placeholder",
      /Nova/,
    );

    // The IPC carried the chosen id. The boot effect issues its own
    // switch_persona for the seeded active persona, so assert the most
    // recent call is the user's choice.
    const calls = await readCalls(page);
    const switches = calls.filter((c) => c.cmd === "switch_persona");
    expect(switches.at(-1)?.args).toMatchObject({ id: "nova" });
  });

  test("hides the switcher when only one persona is installed", async ({
    page,
  }) => {
    await installTauriMock(page, {
      personas: [{ id: "aurora", name: "Aurora" }],
    });
    await page.goto("/");

    await expect(page.getByRole("textbox")).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Persona" })).toHaveCount(0);
  });
});
