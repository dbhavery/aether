import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  applyCue,
  clearCueHistory,
  MAX_CUE_HISTORY,
  pushCue,
  readCueHistory,
} from "./cueHistory";

describe("applyCue (pure)", () => {
  it("ignores empty input", () => {
    expect(applyCue([], "")).toEqual([]);
    expect(applyCue(["hello"], "")).toEqual(["hello"]);
  });

  it("ignores whitespace-only input", () => {
    expect(applyCue(["hello"], "   ")).toEqual(["hello"]);
    expect(applyCue([], "\t\n  ")).toEqual([]);
  });

  it("trims surrounding whitespace before storing", () => {
    expect(applyCue([], "  describe this  ")).toEqual(["describe this"]);
  });

  it("prepends a brand-new cue at the front", () => {
    expect(applyCue(["a"], "b")).toEqual(["b", "a"]);
  });

  it("moves a duplicate cue to the front (newest-wins)", () => {
    expect(applyCue(["a", "b", "c"], "b")).toEqual(["b", "a", "c"]);
  });

  it("treats trimmed-equal cues as duplicates", () => {
    expect(applyCue(["describe this"], "  describe this  ")).toEqual([
      "describe this",
    ]);
  });

  it("caps the list at MAX_CUE_HISTORY", () => {
    const seeds = ["1", "2", "3", "4", "5"];
    expect(MAX_CUE_HISTORY).toBe(5);
    const next = applyCue(seeds, "6");
    expect(next.length).toBe(MAX_CUE_HISTORY);
    expect(next[0]).toBe("6");
    // Oldest entry ("5") is dropped because newest goes to the front.
    expect(next).toEqual(["6", "1", "2", "3", "4"]);
  });

  it("preserves order when the cue already sits at the front", () => {
    expect(applyCue(["a", "b", "c"], "a")).toEqual(["a", "b", "c"]);
  });

  it("is referentially safe — does not mutate the input array", () => {
    const seeds = ["a", "b"];
    const before = [...seeds];
    applyCue(seeds, "c");
    expect(seeds).toEqual(before);
  });
});

describe("pushCue / readCueHistory (localStorage-backed)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it("returns an empty list for a panel that has no history", () => {
    expect(readCueHistory("camera")).toEqual([]);
    expect(readCueHistory("screen")).toEqual([]);
  });

  it("persists pushed cues per panel", () => {
    pushCue("camera", "what is this?");
    pushCue("camera", "and this?");
    expect(readCueHistory("camera")).toEqual(["and this?", "what is this?"]);
  });

  it("keeps camera and screen histories isolated", () => {
    pushCue("camera", "describe this room");
    pushCue("screen", "summarize this slide");
    expect(readCueHistory("camera")).toEqual(["describe this room"]);
    expect(readCueHistory("screen")).toEqual(["summarize this slide"]);
  });

  it("respects the bounded cap when pushing past MAX_CUE_HISTORY", () => {
    for (let i = 1; i <= MAX_CUE_HISTORY + 3; i++) {
      pushCue("camera", `cue-${i}`);
    }
    const list = readCueHistory("camera");
    expect(list.length).toBe(MAX_CUE_HISTORY);
    // Newest pushed is the front; oldest pushed has fallen off the cap.
    expect(list[0]).toBe(`cue-${MAX_CUE_HISTORY + 3}`);
    expect(list).not.toContain("cue-1");
  });

  it("dedupes a re-pushed cue and moves it to the front", () => {
    pushCue("screen", "alpha");
    pushCue("screen", "beta");
    pushCue("screen", "alpha");
    expect(readCueHistory("screen")).toEqual(["alpha", "beta"]);
  });

  it("ignores empty / whitespace-only pushes (caller doesn't have to filter)", () => {
    pushCue("camera", "");
    pushCue("camera", "   ");
    expect(readCueHistory("camera")).toEqual([]);
  });

  it("clearCueHistory wipes only the targeted panel", () => {
    pushCue("camera", "camera-cue");
    pushCue("screen", "screen-cue");
    clearCueHistory("camera");
    expect(readCueHistory("camera")).toEqual([]);
    expect(readCueHistory("screen")).toEqual(["screen-cue"]);
  });

  it("falls back to an empty list when the persisted blob is malformed", () => {
    window.localStorage.setItem("aether.cue-history.camera", "not json");
    expect(readCueHistory("camera")).toEqual([]);
  });

  it("filters non-string entries when reading legacy / corrupted blobs", () => {
    window.localStorage.setItem(
      "aether.cue-history.camera",
      JSON.stringify(["good", 42, "", null, "alsogood"]),
    );
    expect(readCueHistory("camera")).toEqual(["good", "alsogood"]);
  });
});
