import { expect, test, type Page } from "@playwright/test";

import { installTauriMock, readCalls } from "./tauri-mock";

/**
 * Capture panels (Camera / Screen / Voice) — Doctrine §8 used-as-user
 * verification of the media-permission gating on the capture surfaces.
 * The trust-relevant behaviour is "the panel respects the permission
 * posture before touching a device": `deny` blocks, `ask` offers a
 * one-click inline flip, `allow` enables capture. Fake media (configured
 * in playwright.config) lets the allow→start path run without a device.
 */

async function openPanel(page: Page, button: string, panel: string) {
  await expect(page.getByRole("textbox")).toBeVisible();
  await page.getByRole("button", { name: button }).click();
  const region = page.getByRole("complementary", { name: panel });
  await expect(region).toBeVisible();
  return region;
}

async function argsOf(page: Page, cmd: string): Promise<unknown[]> {
  return (await readCalls(page)).filter((c) => c.cmd === cmd).map((c) => c.args);
}

test.describe("capture panels — used-as-user", () => {
  test("camera DENY blocks capture (Start disabled, no getUserMedia path)", async ({
    page,
  }) => {
    await installTauriMock(page, { initialMedia: { camera: "deny" } });
    await page.goto("/");
    const cam = await openPanel(page, "Camera", "Camera");

    await expect(cam.getByText(/set to .*Never.* in/i)).toBeVisible();
    await expect(cam.getByRole("button", { name: "Start camera" })).toBeDisabled();
  });

  test("camera ASK offers a one-click allow that flips the gate", async ({
    page,
  }) => {
    await installTauriMock(page, { initialMedia: { camera: "ask" } });
    await page.goto("/");
    const cam = await openPanel(page, "Camera", "Camera");

    await cam.getByRole("button", { name: "Allow camera" }).click();

    expect(await argsOf(page, "set_media_permission")).toContainEqual({
      kind: "camera",
      stateValue: "allow",
    });
    // After the flip, capture is reachable.
    await expect(
      cam.getByRole("button", { name: "Start camera" }),
    ).toBeEnabled();
  });

  test("camera ALLOW → Start camera goes live and enables analyze", async ({
    page,
  }) => {
    await installTauriMock(page, { initialMedia: { camera: "allow" } });
    await page.goto("/");
    const cam = await openPanel(page, "Camera", "Camera");

    await cam.getByRole("button", { name: "Start camera" }).click();

    // Live indicator flips on (fake device stream), and the analyze
    // action becomes available.
    await expect(cam.getByLabel("camera on")).toBeVisible();
    await expect(
      cam.getByRole("button", { name: "Analyze current frame" }),
    ).toBeEnabled();
  });

  test("microphone DENY blocks recording", async ({ page }) => {
    await installTauriMock(page, { initialMic: "deny" });
    await page.goto("/");
    const voice = await openPanel(page, "Voice", "Voice");

    await expect(voice.getByText(/set to .*Never.* in/i)).toBeVisible();
  });

  test("microphone ASK offers a one-click allow that flips the gate", async ({
    page,
  }) => {
    await installTauriMock(page, { initialMic: "ask" });
    await page.goto("/");
    const voice = await openPanel(page, "Voice", "Voice");

    await voice.getByRole("button", { name: "Allow microphone" }).click();

    expect(await argsOf(page, "set_mic_permission")).toContainEqual({
      stateValue: "allow",
    });
  });

  test("screen DENY blocks capture", async ({ page }) => {
    await installTauriMock(page, { initialMedia: { screen: "deny" } });
    await page.goto("/");
    const screen = await openPanel(page, "Screen", "Screen");

    await expect(screen.getByText(/set to .*Never.* in/i)).toBeVisible();
  });
});
