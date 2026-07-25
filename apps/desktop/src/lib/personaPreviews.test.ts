// Pure-logic tests for the bundled-preview loader.
//
// `loadPersonaPreviews` is the contract between the build pipeline
// (`tools/build-persona-previews/build.py`) and the wizard
// component. The wizard's own tests exercise the loader transitively;
// this file pins the loader's *direct* contract so a build-pipeline
// schema drift surfaces with a focused test failure rather than a
// confusing wizard render error.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  loadPersonaPreviews,
  previewAssetUrl,
  type PersonaPreview,
} from "./personaPreviews";

const INDEX_PATH = "/personas-previews/index.json";

function asResp(body: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? "OK" : "Internal Server Error",
    json: async () => body,
  } as Response;
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("previewAssetUrl", () => {
  it("prefixes a relative path with /personas-previews/", () => {
    expect(previewAssetUrl("aurora/preview.webp")).toBe(
      "/personas-previews/aurora/preview.webp",
    );
  });

  it("does not collapse leading-slash quirks — relative paths stay relative", () => {
    // The loader emits relative paths (e.g. "aurora/preview.webp").
    // Callers should never pass an already-absolute URL, but if they
    // do, the helper should not silently mangle it. Documenting the
    // current behavior so a future refactor doesn't regress.
    expect(previewAssetUrl("/aurora/preview.webp")).toBe(
      "/personas-previews//aurora/preview.webp",
    );
  });
});

describe("loadPersonaPreviews", () => {
  it("returns the personas array from a well-formed index", async () => {
    const fixture = {
      schema_version: 1,
      personas: [
        {
          slug: "aurora",
          display_name: "Aurora Nash",
          tagline: "Warm and grounded.",
          archetype: "warm_supportive",
          preview_webp: "aurora/preview.webp",
          preview_voice_opus: "aurora/preview_voice.opus",
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input) === INDEX_PATH) return asResp(fixture);
        throw new Error(`unexpected fetch: ${String(input)}`);
      }),
    );

    const personas: PersonaPreview[] = await loadPersonaPreviews();
    expect(personas).toHaveLength(1);
    expect(personas[0].slug).toBe("aurora");
    expect(personas[0].display_name).toBe("Aurora Nash");
  });

  it("throws on a non-2xx fetch with the status visible", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => asResp(null, false)),
    );
    await expect(loadPersonaPreviews()).rejects.toThrow(
      /failed to fetch persona preview index: 500/,
    );
  });

  it("throws when the body is missing the personas array", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => asResp({ schema_version: 1 })),
    );
    await expect(loadPersonaPreviews()).rejects.toThrow(/unexpected shape/);
  });

  it("throws when an entry is missing required identity fields", async () => {
    const broken = {
      schema_version: 1,
      personas: [
        {
          // slug missing on purpose
          display_name: "Anon",
          archetype: "warm_supportive",
          preview_webp: "anon/preview.webp",
          preview_voice_opus: "anon/preview_voice.opus",
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => asResp(broken)),
    );
    await expect(loadPersonaPreviews()).rejects.toThrow(/required fields/);
  });
});
