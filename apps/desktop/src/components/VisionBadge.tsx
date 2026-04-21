import { useEffect, useState } from "react";

import { visionStatus } from "../lib/api";
import type { VisionStatus } from "../lib/types";

interface Props {
  refreshKey?: number;
}

/**
 * Tiny status badge for the camera/screen panels. Tells the user
 * whether the next "Analyze" call will hit a real vision-capable
 * model (configured via AETHER_OLLAMA_VISION_MODEL) or fall back to
 * the text-only path that ignores the pixels.
 */
export function VisionBadge({ refreshKey }: Props) {
  const [status, setStatus] = useState<VisionStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    visionStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled) setStatus({ enabled: false, label: null });
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!status) return null;

  if (status.enabled) {
    return (
      <div className="rounded-md border border-aether-ok/40 bg-aether-ok/5 px-3 py-2 text-[11.5px] text-aether-ok">
        <div className="font-medium">Vision provider attached</div>
        <div className="mt-0.5 font-mono text-[10.5px] text-aether-muted">
          {status.label}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-2 text-[11.5px] text-aether-muted">
      <div className="font-medium text-aether-text">No vision provider</div>
      <div className="mt-0.5">
        Analyze will run the active text model on your note only — the
        pixels are not sent. Set{" "}
        <code className="font-mono">AETHER_OLLAMA_VISION_MODEL</code> to a
        vision-capable model (e.g. <code className="font-mono">llava</code>
        ) and restart Aether to enable.
      </div>
    </div>
  );
}
