import { expect, test, type Page } from "@playwright/test";

import { installTauriMock, readCalls } from "./tauri-mock";

/**
 * Media + mic permission tri-state (Settings) — Doctrine §8 used-as-user
 * verification of the camera/screen/microphone permission gates. Same
 * trust-gate shape as the autonomy + memory gates: the UI reflects the
 * persisted state and each change is pushed over IPC.
 */

async function openSettings(page: Page) {
  await expect(page.getByRole("textbox")).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(
    page.getByRole("radiogroup", { name: "Camera permission" }),
  ).toBeVisible();
}

async function setArgs(page: Page, cmd: string): Promise<unknown[]> {
  return (await readCalls(page)).filter((c) => c.cmd === cmd).map((c) => c.args);
}

test.describe("media + mic permissions — used-as-user", () => {
  test("reflects persisted permissions on open", async ({ page }) => {
    await installTauriMock(page, {
      initialMedia: { camera: "allow", screen: "deny" },
      initialMic: "ask",
    });
    await page.goto("/");
    await openSettings(page);

    const camera = page.getByRole("radiogroup", { name: "Camera permission" });
    await expect(camera.getByRole("radio", { name: "Allow" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    const screen = page.getByRole("radiogroup", { name: "Screen permission" });
    await expect(screen.getByRole("radio", { name: "Never" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    const microphone = page.getByRole("radiogroup", {
      name: "Microphone permission",
    });
    await expect(
      microphone.getByRole("radio", { name: "Ask" }),
    ).toHaveAttribute("aria-checked", "true");
  });

  test("changing camera/screen/mic pushes the right IPC and marks it active", async ({
    page,
  }) => {
    await installTauriMock(page); // all default to "ask"
    await page.goto("/");
    await openSettings(page);

    const camera = page.getByRole("radiogroup", { name: "Camera permission" });
    await camera.getByRole("radio", { name: "Allow" }).click();
    await expect(camera.getByRole("radio", { name: "Allow" })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    const screen = page.getByRole("radiogroup", { name: "Screen permission" });
    await screen.getByRole("radio", { name: "Never" }).click();
    await expect(screen.getByRole("radio", { name: "Never" })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    const microphone = page.getByRole("radiogroup", {
      name: "Microphone permission",
    });
    await microphone.getByRole("radio", { name: "Allow" }).click();
    await expect(
      microphone.getByRole("radio", { name: "Allow" }),
    ).toHaveAttribute("aria-checked", "true");

    const mediaArgs = await setArgs(page, "set_media_permission");
    expect(mediaArgs).toContainEqual({ kind: "camera", stateValue: "allow" });
    expect(mediaArgs).toContainEqual({ kind: "screen", stateValue: "deny" });
    expect(await setArgs(page, "set_mic_permission")).toContainEqual({
      stateValue: "allow",
    });
  });
});
