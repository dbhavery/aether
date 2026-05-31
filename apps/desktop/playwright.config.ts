import { defineConfig, devices } from "@playwright/test";

/**
 * Wave 19 (T1.3 carryover) — Doctrine §8 used-as-user verification harness.
 *
 * Drives the real Vite-served frontend in Chromium and exercises the
 * Wave 14/15 approval modal end-to-end as a user would: type a turn,
 * watch the gate raise the modal, pick a temporal scope, submit, and
 * assert the `resolve_approval` IPC carried the right `UserChoice`.
 *
 * This covers what the vitest+RTL suite (16 ApprovalModal cases) cannot:
 * real DOM, real CSS layout/visibility, real focus + keyboard wiring,
 * and the full App.tsx state-machine path from `submit_turn` →
 * `pendingApproval` → modal mount → `resolve_approval`.
 *
 * The Tauri runtime is absent in a browser, so `e2e/tauri-mock.ts`
 * installs a `window.__TAURI_INTERNALS__` shim via `addInitScript`
 * BEFORE the bundle loads (the app calls `companion_banner` /
 * `presence_current` / `list_personas` on mount). The shim matches the
 * @tauri-apps/api@2.10.1 invoke contract verified against the installed
 * `core.js` (`invoke(cmd, args, options)` delegates to
 * `window.__TAURI_INTERNALS__.invoke`).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e/.report" }]],
  outputDir: "e2e/.artifacts",
  use: {
    baseURL: "http://localhost:1420",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Grant + fake camera/mic so the capture panels' allow→start
        // paths exercise getUserMedia without a real device or prompt.
        permissions: ["camera", "microphone"],
        launchOptions: {
          args: [
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
          ],
        },
      },
    },
  ],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:1420",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
