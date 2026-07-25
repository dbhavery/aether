import type { Config } from "tailwindcss";

/**
 * Tailwind tokens bound to `packages/ui-kit/src/tokens.ts` so the shell's
 * palette tracks the shared design system. Dark-first, monochrome, no
 * indigo-purple AI slop (ARCHITECTURE.md — what the UI is NOT).
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        aether: {
          bg: "#0a0a0b",
          surface: "#111113",
          raised: "#16161a",
          elevated: "#1c1c21",
          text: "#e7e7ea",
          muted: "#9a9aa2",
          dim: "#6c6c74",
          border: "#222228",
          borderHi: "#2c2c34",
          accent: "#c9c9d1", // near-white, warm-grey — no blue cast
          focus: "#e7e7ea",
          ok: "#7ab893",
          warn: "#d6b76b",
          err: "#d98c7a",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        neu: "inset 1px 1px 2px rgba(255,255,255,0.03), inset -1px -1px 2px rgba(0,0,0,0.45), 0 1px 0 rgba(255,255,255,0.02)",
        neuRaised:
          "inset 0 1px 0 rgba(255,255,255,0.04), 0 1px 0 rgba(0,0,0,0.6), 0 4px 12px rgba(0,0,0,0.35)",
        neuInset:
          "inset 2px 2px 5px rgba(0,0,0,0.55), inset -1px -1px 2px rgba(255,255,255,0.02)",
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
        xl: "20px",
      },
      keyframes: {
        pulseDot: {
          "0%, 100%": { opacity: "0.55", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.15)" },
        },
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        wizardBar: {
          "0%, 100%": { transform: "scaleY(0.35)" },
          "50%": { transform: "scaleY(1)" },
        },
      },
      animation: {
        pulseDot: "pulseDot 1.6s ease-in-out infinite",
        fadeIn: "fadeIn 140ms ease-out",
        wizardBar: "wizardBar 0.9s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
