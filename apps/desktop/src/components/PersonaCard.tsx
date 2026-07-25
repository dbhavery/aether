import type { CompanionBanner } from "../lib/types";

/**
 * Compact identity card rendered once at the top of the conversation on a
 * fresh session. Keeps the persona visible without shouting — aligns with
 * the design language in ARCHITECTURE.md ("restrained, warm").
 */
export function PersonaCard({ banner }: { banner: CompanionBanner }) {
  return (
    <div className="neu-surface mx-auto my-6 max-w-xl rounded-lg px-5 py-4 animate-fadeIn">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Companion
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <h2 className="text-[15px] font-medium text-aether-text">
              {banner.persona_name}
            </h2>
            <span className="text-[11px] font-mono text-aether-dim">
              v{banner.persona_version} · {banner.output_detail}
            </span>
          </div>
        </div>
        <div className="rounded-sm border border-aether-border px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-aether-muted">
          {banner.preferred_tier}
        </div>
      </div>
      <p className="mt-3 text-[12.5px] leading-relaxed text-aether-muted">
        {banner.tagline}
      </p>
    </div>
  );
}
