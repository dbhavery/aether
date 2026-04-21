import { defineConfig } from "vitest/config";

// Vitest config for the desktop shell.
//
// Two flavours of test live alongside each other:
//
// 1. Pure-logic unit tests under `src/lib/*.test.ts` — cue history,
//    media-turn classification, etc. No DOM, no React.
// 2. Component tests under `src/**/*.test.tsx` — React Testing
//    Library renders against jsdom; the api.ts wrapper around Tauri
//    `invoke` is mocked per-test so tests don't need a Tauri runtime.
//
// `setupFiles` registers RTL's auto-cleanup so tests don't leak DOM
// state across runs.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
  },
});
