import { defineConfig } from "vitest/config";

// Minimal Vitest config for pure-logic unit tests under src/lib and
// adjacent helpers. We deliberately do NOT set up React Testing
// Library / component rendering here — the cue history and
// media-turn classification surfaces are pure functions and that's
// the scope of this harness.
//
// `jsdom` is the environment so `localStorage`-touching code can
// run unmodified inside tests.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    globals: false,
  },
});
