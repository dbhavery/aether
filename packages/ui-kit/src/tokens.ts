// Design tokens — dark-first neumorphic monochrome.
// Placeholder values; the real palette is locked in a later wave against
// ARCHITECTURE.md (the component system / UX principles) and Don's design research.

export interface Tokens {
  readonly color: {
    readonly bg: string;
    readonly surface: string;
    readonly surfaceRaised: string;
    readonly text: string;
    readonly textMuted: string;
    readonly accent: string;
    readonly border: string;
  };
  readonly radius: {
    readonly sm: string;
    readonly md: string;
    readonly lg: string;
  };
  readonly space: readonly string[];
}

export const tokens: Tokens = {
  color: {
    bg: "#0a0a0b",
    surface: "#111113",
    surfaceRaised: "#16161a",
    text: "#e7e7ea",
    textMuted: "#9a9aa2",
    accent: "#6b7bff",
    border: "#222228",
  },
  radius: { sm: "6px", md: "10px", lg: "16px" },
  space: ["0", "4px", "8px", "12px", "16px", "24px", "32px", "48px", "64px"],
} as const;
