// Phase 6 UX audit Bug 5.1 regression lock.
//
// At the dev build's default 976 px window width, the header chrome
// must stay on a single line: route badge does not wrap, presence
// label does not clip. We assert structural shape (single flex row,
// `flex-nowrap`, responsive collapse classes) rather than measured
// pixels because jsdom does not lay out — pixel-correct render is
// validated by Don's eyeball at the live shell. The structural
// invariants here are sufficient to catch the regression mode the
// audit observed (a missing `flex-nowrap` or a re-introduced `flex-
// wrap` on the header row would fail this test).

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { Header } from "./Header";
import type {
  CompanionBanner,
  PersonaCatalogEntry,
  PresencePayload,
} from "../lib/types";

const banner: CompanionBanner = {
  persona_id: "aurora-v1",
  persona_name: "Aurora v1",
  persona_version: "1",
  preferred_tier: "forge",
  provider_mode: "reflex_stub",
  provider_label: "Reflex stub (no model)",
  output_detail: "balanced",
  tagline: "Warm and grounded.",
  system_prompt: "",
};

const presence: PresencePayload = {
  state: "quiet",
  detail: null,
  updated_at_ms: 0,
};

const personas: PersonaCatalogEntry[] = [
  {
    id: "aurora-v1",
    name: "Aurora v1",
    tagline: "Warm and grounded.",
    stance: "balanced",
    tone: "warm",
  },
];

function renderHeader() {
  return render(
    <Header
      banner={banner}
      presence={presence}
      personas={personas}
      onOpenMemory={() => {}}
      onOpenTrust={() => {}}
      onOpenSettings={() => {}}
      onOpenCamera={() => {}}
      onOpenScreen={() => {}}
      onOpenVoice={() => {}}
      onReopenDisclosure={() => {}}
      onClearSession={() => {}}
      onSwitchPersona={() => {}}
    />,
  );
}

describe("Header — Phase 6 UX audit Bug 5.1 regression", () => {
  it("renders the header row with flex-nowrap so chrome never wraps", () => {
    const { getByTestId } = renderHeader();
    const header = getByTestId("app-header");
    expect(header.className).toContain("flex-nowrap");
  });

  it("uses tighter padding under the lg (1024 px) breakpoint", () => {
    const { getByTestId } = renderHeader();
    const header = getByTestId("app-header");
    // The narrow-width default must be smaller than the lg: variant.
    expect(header.className).toContain("px-3");
    expect(header.className).toContain("lg:px-5");
    expect(header.className).toContain("py-2");
    expect(header.className).toContain("lg:py-3");
  });

  it("renders the provider label with truncate + nowrap to defend against multi-line wrap", () => {
    const { getByTitle } = renderHeader();
    // The provider badge sets `title` to the full label so hover
    // recovers the text after truncation kicks in.
    const wrap = getByTitle("Reflex stub (no model)");
    expect(wrap.className).toContain("min-w-0");
    const labelSpan = wrap.querySelector("span.truncate");
    expect(labelSpan).toBeTruthy();
    expect(labelSpan?.className).toContain("whitespace-nowrap");
  });
});
