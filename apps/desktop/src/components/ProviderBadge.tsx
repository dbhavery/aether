import type { CompanionBanner } from "../lib/types";

/**
 * Small header badge that tells the user which backend is answering.
 * Local-first doctrine requires this to be visible, not buried — see
 * ARCHITECTURE.md ("local-first where possible").
 */
export function ProviderBadge({ banner }: { banner: CompanionBanner }) {
  const isStub = banner.provider_mode === "reflex_stub";
  return (
    // `min-w-0` + `truncate` lets the parent flex container shrink the
    // label rather than wrap it. `whitespace-nowrap` on the label
    // itself defends against the badge wrapping into 2-3 lines at
    // narrow widths (Phase 6 UX audit Bug 5.1, observed at 976 px).
    // The full label remains in `title` so hover recovers the text.
    <div className="flex min-w-0 items-center gap-2" title={banner.provider_label}>
      <span
        className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
          isStub ? "bg-aether-dim" : "bg-aether-ok"
        }`}
        aria-hidden
      />
      <span className="truncate whitespace-nowrap text-[11px] font-mono text-aether-muted">
        {banner.provider_label}
      </span>
    </div>
  );
}
