import { expect, test, type Page } from "@playwright/test";

import { installTauriMock, readCalls } from "./tauri-mock";

/**
 * T2.5 — Doctrine §8 used-as-user verification of the Trust drawer
 * Memory tab. The §8 gate for this surface is historically satisfied;
 * this hardens it with reproducible browser coverage of the load,
 * the Auto-domain forget/edit happy paths (mutation reflected on
 * refresh), and the Ask-domain (user-sensitive) approval flow.
 */

/** Open the Trust drawer on the Memory tab via the header button. */
async function openMemory(page: Page) {
  await expect(page.getByRole("textbox")).toBeVisible(); // app booted
  await page.getByRole("button", { name: "Memory" }).click();
  // Lanes render as labelled regions; wait for the session lane.
  await expect(
    page.getByRole("region", { name: "Memory domain session" }),
  ).toBeVisible();
}

async function callArgs(page: Page, cmd: string): Promise<unknown[]> {
  const calls = await readCalls(page);
  return calls.filter((c) => c.cmd === cmd).map((c) => c.args);
}

test.describe("memory tab — used-as-user (T2.5)", () => {
  test("renders all six domain lanes, items, and honest empty states", async ({
    page,
  }) => {
    await installTauriMock(page);
    await page.goto("/");
    await openMemory(page);

    for (const domain of [
      "session",
      "durable",
      "facts",
      "projects",
      "preferences",
      "artifacts",
    ]) {
      await expect(
        page.getByRole("region", { name: `Memory domain ${domain}` }),
      ).toBeVisible();
    }

    // Auto (session) lane shows its seeded item.
    const session = page.getByRole("region", { name: "Memory domain session" });
    await expect(session.getByText("Remember to water the plants.")).toBeVisible();

    // An unbacked domain shows the honest empty-state copy, not invented rows.
    const durable = page.getByRole("region", { name: "Memory domain durable" });
    await expect(durable.getByText(/Storage for this domain arrives/)).toBeVisible();
  });

  test("Auto-domain forget removes the item (mutation reflected on refresh)", async ({
    page,
  }) => {
    await installTauriMock(page);
    await page.goto("/");
    await openMemory(page);

    const item = page.getByRole("article", { name: "Memory item mem-session-1" });
    await expect(item).toBeVisible();
    await item.getByRole("button", { name: "Forget" }).click();

    // Single-call Auto path — no approval dialog — and the item is gone.
    await expect(
      page.getByRole("article", { name: "Memory item mem-session-1" }),
    ).toHaveCount(0);
    expect(await callArgs(page, "memory_forget_item")).toContainEqual({
      domain: "session",
      memoryId: "mem-session-1",
    });
    expect(await callArgs(page, "memory_forget_item_after_approval")).toEqual([]);
  });

  test("Ask-domain forget routes through the approval dialog", async ({
    page,
  }) => {
    await installTauriMock(page);
    await page.goto("/");
    await openMemory(page);

    const fact = page.getByRole("article", { name: "Memory item mem-facts-1" });
    await expect(fact).toBeVisible();
    await fact.getByRole("button", { name: "Forget" }).click();

    // User-sensitive: confirmation dialog, not an immediate delete.
    const dialog = page.getByRole("dialog", { name: "Forget this item?" });
    await expect(dialog).toBeVisible();
    await expect(
      page.getByRole("article", { name: "Memory item mem-facts-1" }),
    ).toBeVisible(); // still present pre-approval

    await dialog.getByRole("button", { name: "Approve once" }).click();

    await expect(
      page.getByRole("article", { name: "Memory item mem-facts-1" }),
    ).toHaveCount(0);
    expect(await callArgs(page, "memory_forget_item_after_approval")).toContainEqual(
      { domain: "facts", memoryId: "mem-facts-1" },
    );
  });

  test("Auto-domain edit rewrites the item content", async ({ page }) => {
    await installTauriMock(page);
    await page.goto("/");
    await openMemory(page);

    const item = page.getByRole("article", { name: "Memory item mem-session-1" });
    await item.getByRole("button", { name: "Edit" }).click();

    const editor = item.getByRole("textbox", { name: "Edit memory content" });
    await expect(editor).toBeVisible();
    await editor.fill("Water the plants on Tuesdays.");
    await item.getByRole("button", { name: "Save" }).click();

    const session = page.getByRole("region", { name: "Memory domain session" });
    await expect(session.getByText("Water the plants on Tuesdays.")).toBeVisible();
    expect(await callArgs(page, "memory_edit")).toContainEqual({
      domain: "session",
      memoryId: "mem-session-1",
      newContent: "Water the plants on Tuesdays.",
    });
  });
});
