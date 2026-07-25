// Vitest setup — runs once per worker before any test file.
//
// Registers React Testing Library's per-test cleanup so the jsdom
// document is reset between tests. Without this, leftover DOM nodes
// from one test can leak into the next and cause confusing query
// failures.

import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
