import type { Config } from "tailwindcss";

/**
 * Tailwind v3 config exposing the CSS-variable design tokens as utility classes.
 * All tokens live in app/globals.css under :root (see that file for canonical defs).
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  darkMode: "class", // dark-only ships; class left as the toggle surface
  theme: {
    extend: {
      colors: {
        "bg-0": "var(--bg-0)",
        "bg-1": "var(--bg-1)",
        "bg-2": "var(--bg-2)",
        "bg-3": "var(--bg-3)",
        "bg-4": "var(--bg-4)",
        "fg-primary": "var(--fg-primary)",
        "fg-secondary": "var(--fg-secondary)",
        "fg-muted": "var(--fg-muted)",
        "fg-disabled": "var(--fg-disabled)",
        "border-subtle": "var(--border-subtle)",
        "border-default": "var(--border-default)",
        "border-strong": "var(--border-strong)",
        accent: "var(--accent)",
        "accent-hover": "var(--accent-hover)",
        "accent-muted": "var(--accent-muted)",
        ok: "var(--ok)",
        warn: "var(--warn)",
        error: "var(--error)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      boxShadow: {
        raised: "var(--shadow-raised)",
        inset: "var(--shadow-inset)",
        float: "var(--shadow-float)",
      },
      fontFamily: {
        sans: [
          "var(--font-plex)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "JetBrains Mono",
          "Fira Code",
          "Menlo",
          "monospace",
        ],
      },
      maxWidth: {
        content: "var(--content-max)",
        wizard: "var(--wizard-max)",
      },
      transitionTimingFunction: {
        "out-soft": "var(--ease-out)",
        "in-out-soft": "var(--ease-in-out)",
      },
      transitionDuration: {
        fast: "140ms",
        med: "260ms",
        slow: "420ms",
      },
    },
  },
  plugins: [],
};

export default config;
