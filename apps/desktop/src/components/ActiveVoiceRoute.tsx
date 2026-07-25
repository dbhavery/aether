import { useEffect, useState } from "react";

import { voiceStatus } from "../lib/api";
import type { VoiceStatus } from "../lib/types";
import { speechProviderShortLabel } from "../lib/speechProviders";

interface Props {
  refreshKey?: number;
}

/**
 * Compact one-liner placed above the Record button on the VoicePanel
 * so the user can see, at the point of action, what STT route the
 * next transcribe_utterance call will take. Mirrors
 * `ActiveVisionRoute` but with one key difference: voice has no
 * text-only fallback, so "disabled" is a loud state — the user
 * needs to know the next record will error.
 */
export function ActiveVoiceRoute({ refreshKey }: Props) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    voiceStatus()
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
  const text = formatVoiceRouteHint(status);
  const tone = status.enabled ? "text-aether-ok" : "text-aether-warn";

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

/** Pure helper exposed for unit tests so the wording can be locked. */
export function formatVoiceRouteHint(status: VoiceStatus): string {
  if (!status.enabled) {
    return "Voice disabled — configure a speech provider";
  }
  const provider = speechRouteLabel(status.active_id, status.label);
  if (status.active_model && status.active_model.length > 0) {
    return `${provider} · ${status.active_model}`;
  }
  return provider;
}

/** Short, plain-language provider label — thin wrapper over the
 * shared registry with a graceful fallback. */
export function speechRouteLabel(
  id: string | null,
  label: string | null,
): string {
  return speechProviderShortLabel(id) ?? label ?? id ?? "Voice";
}
