import { useEffect, useState } from "react";

import { visionStatus } from "../lib/api";
import type { VisionStatus } from "../lib/types";
import { visionProviderShortLabel } from "../lib/visionProviders";

interface Props {
  /** Bumping this number forces the hint to re-fetch — handy when a
   * sibling control (the VisionBadge dropdown / refresh button) just
   * mutated the active provider or model. */
  refreshKey?: number;
}

/**
 * Compact one-liner placed above the Analyze button on each capture
 * panel so the user can see, at the point of action, what route the
 * next analyze call will take.
 *
 * Three states:
 *   - "→ <provider> · <model>"  when vision is enabled and a model
 *     id is known,
 *   - "→ <provider>" when vision is enabled but the adapter can't
 *     report a model (passive adapter / discovery failure),
 *   - "→ Text-only fallback" when no vision provider is active.
 *
 * The badge above already shows full label + selection controls; this
 * is purely a "where is the next click going?" reminder. Keep it
 * short, accessible, and visually quiet — no chips, no buttons.
 */
export function ActiveVisionRoute({ refreshKey }: Props) {
  const [status, setStatus] = useState<VisionStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    visionStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled)
          setStatus({
            enabled: false,
            active_id: null,
            label: null,
            active_model: null,
            providers: [],
          });
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!status) return null;
  const text = formatRouteHint(status);
  const tone = status.enabled
    ? "text-aether-ok"
    : "text-aether-muted";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`mt-3 flex items-center gap-1.5 font-mono text-[11px] ${tone}`}
    >
      <span aria-hidden="true">→</span>
      <span className="truncate">{text}</span>
    </div>
  );
}

/**
 * Format the route hint string. Pure helper exposed for unit tests so
 * the wording can be locked without rendering React.
 */
export function formatRouteHint(status: VisionStatus): string {
  if (!status.enabled) {
    return "Text-only fallback";
  }
  const provider = providerShortLabel(status.active_id, status.label);
  if (status.active_model && status.active_model.length > 0) {
    return `${provider} · ${status.active_model}`;
  }
  return provider;
}

/**
 * Pull a short, plain-language provider label out of either the wire
 * id or the longer human label. The full label is suitable for the
 * VisionBadge header but too long for the hint line.
 *
 * Looks the id up in the shared `visionProviderShortLabel` registry
 * first; falls back to the long label, then the id, then a generic
 * "Vision" string for adapters that aren't yet in the registry.
 * Kept as a thin wrapper so existing call sites and tests don't move.
 */
export function providerShortLabel(
  id: string | null,
  label: string | null,
): string {
  return visionProviderShortLabel(id) ?? label ?? id ?? "Vision";
}
