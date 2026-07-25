import { expect, test } from "@playwright/test";

import { installTauriMock } from "./tauri-mock";

/**
 * Chat turn outcomes — Doctrine §8 used-as-user verification of the
 * "no silent fallback" hard rule (transport/parse/provider errors must
 * surface visibly). Drives a real turn through the chat input and
 * asserts both the happy reply and the visible failure path.
 */

test.describe("chat turn outcome — used-as-user", () => {
  test("a completed turn renders the assistant reply", async ({ page }) => {
    await installTauriMock(page); // submit_turn → completed
    await page.goto("/");

    const input = page.getByRole("textbox");
    await expect(input).toBeVisible();
    await input.fill("hello");
    await input.press("Enter");

    await expect(page.getByText("Done.")).toBeVisible();
  });

  test("a failing turn surfaces the error visibly and re-enables input", async ({
    page,
  }) => {
    await installTauriMock(page, { submitError: "provider unreachable" });
    await page.goto("/");

    const input = page.getByRole("textbox");
    await expect(input).toBeVisible();
    await input.fill("hello");
    await input.press("Enter");

    // No silent fallback: the failure is shown in the transcript…
    await expect(page.getByText(/Something went wrong/)).toBeVisible();
    await expect(page.getByText(/provider unreachable/)).toBeVisible();
    // …and the user is not stuck — the input recovers for a retry.
    await expect(input).toBeEnabled();
  });
});
