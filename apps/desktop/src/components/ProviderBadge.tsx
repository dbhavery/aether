import type { CompanionBanner } from "../lib/types";

/**
 * Small header badge that tells the user which backend is answering.
 * Local-first doctrine requires this to be visible, not buried — see
 * planning/03_vision_and_thesis §"Local-first where possible".
 */
export function ProviderBadge({ banner }: { banner: CompanionBanner }) {
  const isStub = banner.provider_mode === "reflex_stub";
  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${
          isStub ? "bg-aether-dim" : "bg-aether-ok"
        }`}
        aria-hidden
      />
      <span className="text-[11px] font-mono text-aether-muted">
        {banner.provider_label}
      </span>
    </div>
  );
}
