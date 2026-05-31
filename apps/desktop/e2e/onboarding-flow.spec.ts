import { expect, test } from "@playwright/test";

import { installTauriMock, readCalls } from "./tauri-mock";

/**
 * Onboarding flow — Doctrine §8 used-as-user verification of the
 * first-run path a brand-new user hits: PersonaWizard → Disclosure →
 * PresetPicker → chat shell. The other specs seed past these gates;
 * this one drives them (`freshUser: true`), covering the surface the
 * rest of the harness bypasses.
 */

test.describe("onboarding flow — used-as-user (first run)", () => {
  test("a new user walks wizard → disclosure → preset into the chat shell", async ({
    page,
  }) => {
    await installTauriMock(page, { freshUser: true });
    await page.goto("/");

    // 1. PersonaWizard (full screen, no gates acked).
    await expect(
      page.getByRole("heading", { name: /Meet your companion/i }),
    ).toBeVisible();
    const card = page.getByRole("button", { name: "Pick Aurora Nash" });
    await expect(card).toBeVisible();

    // CTA is disabled until a companion is picked.
    const pickCta = page.getByRole("button", {
      name: "Pick a companion to continue",
    });
    await expect(pickCta).toBeDisabled();

    await card.click();
    await expect(card).toHaveAttribute("aria-pressed", "true");

    // 2. Pick CTA → confirm step.
    await page.getByRole("button", { name: "Continue with Aurora Nash" }).click();
    await expect(page.getByText("You picked Aurora Nash")).toBeVisible();
    await page
      .getByRole("button", { name: "Continue with Aurora", exact: true })
      .click();

    // Commit switched to the chosen persona over IPC.
    const switches = (await readCalls(page)).filter(
      (c) => c.cmd === "switch_persona",
    );
    expect(switches.at(-1)?.args).toMatchObject({ id: "aurora" });

    // 3. Disclosure (welcome) overlay on the now-rendered shell.
    const disclosure = page.getByRole("dialog", { name: /Welcome to Companion/i });
    await expect(disclosure).toBeVisible();
    await disclosure
      .getByRole("button", { name: "I understand — let's start" })
      .click();
    await expect(disclosure).toBeHidden();

    // 4. PresetPicker overlay.
    const preset = page.getByRole("dialog", {
      name: /How much autonomy should Companion have/i,
    });
    await expect(preset).toBeVisible();
    // "Assistant" is the default selection; commit it directly (per-option
    // selection is covered exhaustively by autonomy-preset.spec.ts).
    await preset.getByRole("button", { name: /^Use Assistant/ }).click();

    // Choice pushed to the backend.
    const presetCalls = (await readCalls(page))
      .filter((c) => c.cmd === "set_autonomy_preset")
      .map((c) => c.args);
    expect(presetCalls).toContainEqual({ preset: "assistant" });

    // 5. Landed on the chat shell — onboarding fully dismissed.
    await expect(page.getByRole("textbox")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("'I'll decide later' clears the overlay (null) and still lands on chat", async ({
    page,
  }) => {
    await installTauriMock(page, { freshUser: true });
    await page.goto("/");

    await page.getByRole("button", { name: "Pick Aurora Nash" }).click();
    await page.getByRole("button", { name: "Continue with Aurora Nash" }).click();
    await page
      .getByRole("button", { name: "Continue with Aurora", exact: true })
      .click();
    await page
      .getByRole("dialog", { name: /Welcome to Companion/i })
      .getByRole("button", { name: "I understand — let's start" })
      .click();

    const preset = page.getByRole("dialog", {
      name: /How much autonomy should Companion have/i,
    });
    await preset.getByRole("button", { name: "I'll decide later" }).click();

    const presetCalls = (await readCalls(page))
      .filter((c) => c.cmd === "set_autonomy_preset")
      .map((c) => c.args);
    expect(presetCalls).toContainEqual({ preset: null });
    await expect(page.getByRole("textbox")).toBeVisible();
  });
});
