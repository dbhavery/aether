import { describe, expect, it } from "vitest";

import { truncateForDisplay, truncateMiddleForDisplay } from "./displayString";

describe("truncateForDisplay", () => {
  it("returns the original string when shorter than max", () => {
    expect(truncateForDisplay("llava:latest", 32)).toBe("llava:latest");
  });

  it("returns the original string when exactly max", () => {
    const exact = "abcdefghij"; // length 10
    expect(truncateForDisplay(exact, 10)).toBe(exact);
  });

  it("truncates with ellipsis when longer than max", () => {
    const long = "qwen2.5-vl-72b-instruct-q4_k_m"; // length 30
    const out = truncateForDisplay(long, 16);
    expect(out).toBe("qwen2.5-vl-72b-…");
    expect(out.length).toBe(16);
    expect(out.endsWith("…")).toBe(true);
  });

  it("clamps tiny max values up so it never returns an empty string", () => {
    expect(truncateForDisplay("hello", 0)).toBe("…");
    expect(truncateForDisplay("hello", -3)).toBe("…");
  });

  it("leaves an empty input untouched", () => {
    expect(truncateForDisplay("", 10)).toBe("");
  });
});

describe("truncateMiddleForDisplay", () => {
  it("returns the original string when shorter than max", () => {
    expect(truncateMiddleForDisplay("llava:latest", 28)).toBe("llava:latest");
  });

  it("preserves the suffix when truncating a long quantized model id", () => {
    const long = "qwen2.5-vl-72b-instruct-q4_k_m"; // length 30
    const out = truncateMiddleForDisplay(long, 28, 8);
    expect(out.length).toBe(28);
    expect(out).toContain("…");
    expect(out.endsWith("t-q4_k_m")).toBe(true);
    expect(out.startsWith("qwen2.5-vl-72b-inst")).toBe(true);
  });

  it("clamps max up so the prefix always gets at least one character", () => {
    const out = truncateMiddleForDisplay("abcdefghijklmnop", 4, 8);
    // suffixLen 8 → minimum width 10 (8 + 2). Result reads
    // "a…ijklmnop" — prefix gets 1 char, ellipsis, last 8.
    expect(out.length).toBe(10);
    expect(out).toBe("a…ijklmnop");
  });

  it("leaves an empty input untouched", () => {
    expect(truncateMiddleForDisplay("", 28)).toBe("");
  });
});
