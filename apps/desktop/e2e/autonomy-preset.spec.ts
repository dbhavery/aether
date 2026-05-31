import { expect, test, type Page } from "@playwright/test";

import { installTauriMock, readCalls } from "./tauri-mock";

/**
 * T2.3 — Doctrine §8 used-as-user verification of the Settings
 * "Autonomy" preset picker. Confirms the picker reflects the persisted
 * preset on open, that selecting each option marks it active and sends
 * `set_autonomy_preset` with the matching value, and that "No override"
 * clears the overlay (null).
 */

/** Open Settings from the header and return the Autonomy radiogroup. */
async function openAutonomy(page: Page) {
  await expect(page.getByRole("textbox")).toBeVisible(); // app booted
  await page.getByRole("button", { name: "Settings" }).click();
  const group = page.getByRole("radiogroup", { name: "Autonomy preset" });
  await expect(group).toBeVisible();
  return group;
}

/** Args of every `set_autonomy_preset` call the app made. */
async function autonomySetArgs(page: Page): Promise<unknown[]> {
  const calls = await readCalls(page);
  return calls.filter((c) => c.cmd === "set_autonomy_preset").map((c) => c.args);
}

test.describe("autonomy preset picker — used-as-user (T2.3)", () => {
  test("reflects the persisted preset on open", async ({ page }) => {
    await installTauriMock(page, { initialAutonomy: "operator" });
    await page.goto("/");
    const group = await openAutonomy(page);

    await expect(
      group.getByRole("radio", { name: "Operator" }),
    ).toHaveAttribute("aria-checked", "true");
  });

  test("a null overlay shows 'No override' as active", async ({ page }) => {
    await installTauriMock(page, { initialAutonomy: null });
    await page.goto("/");
    const group = await openAutonomy(page);

    await expect(
      group.getByRole("radio", { name: "No override" }),
    ).toHaveAttribute("aria-checked", "true");
  });

  test("selecting a preset marks it active and sends the matching value", async ({
    page,
  }) => {
    await installTauriMock(page, { initialAutonomy: null });
    await page.goto("/");
    const group = await openAutonomy(page);

    await group.getByRole("radio", { name: "Observer" }).click();
    await expect(
      group.getByRole("radio", { name: "Observer" }),
    ).toHaveAttribute("aria-checked", "true");

    await group.getByRole("radio", { name: "Operator" }).click();
    await expect(
      group.getByRole("radio", { name: "Operator" }),
    ).toHaveAttribute("aria-checked", "true");

    const args = await autonomySetArgs(page);
    expect(args).toContainEqual({ preset: "observer" });
    expect(args).toContainEqual({ preset: "operator" });
  });

  test("'No override' clears the overlay (null)", async ({ page }) => {
    await installTauriMock(page, { initialAutonomy: "operator" });
    await page.goto("/");
    const group = await openAutonomy(page);

    await group.getByRole("radio", { name: "No override" }).click();
    await expect(
      group.getByRole("radio", { name: "No override" }),
    ).toHaveAttribute("aria-checked", "true");

    const args = await autonomySetArgs(page);
    expect(args).toContainEqual({ preset: null });
  });
});
