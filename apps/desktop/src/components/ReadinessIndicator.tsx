import { useEffect, useState } from "react";
import { embeddingsReadiness } from "../lib/api";
import type { ReadinessState } from "../lib/types";

/**
 * ADR-0007 D6 attention-badge stub.
 *
 * STATUS: Typecheck-only scaffold shipped during 2026-04-24 autonomous
 * validation run. Wires the readiness poll into a tiny dot indicator
 * the chrome can render next to whatever icon Don decides to attach
 * it to (Trust drawer button, Settings drawer button, header pill —
 * placement is a Don decision).
 *
 * Behavior contract (matches ADR-0007 D6 attention-badge semantic):
 *   - Hidden when kind === "ready" or "disabled" (no problem to flag).
 *   - Visible warn-color dot when kind === "not_ready".
 *   - Visible neutral dot when kind === "unknown" (pre-probe).
 *
 * Visual decisions to escalate:
 *   - Dot size, position relative to anchor icon, animation (steady
 *     vs subtle pulse on transition), color tokens — Don's call.
 *   - Where this lives in the chrome — Don's call.
 */

const POLL_INTERVAL_MS = 2_000;

interface Props {
  /** When provided, the indicator wraps the children (anchor element)
   * and overlays the dot in the corner. When omitted, just renders
   * the dot for Don to position via CSS. */
  children?: React.ReactNode;
}

export function ReadinessIndicator({ children }: Props) {
  const [readiness, setReadiness] = useState<ReadinessState | null>(null);

  useEffect(() => {
    let mounted = true;
    async function refresh() {
      try {
        const r = await embeddingsReadiness();
        if (mounted) setReadiness(r);
      } catch {
        // Silent — indicator should never throw into the chrome.
      }
    }
    void refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  if (!readiness) return <>{children ?? null}</>;

  // No badge needed when retrieval is healthy or intentionally off.
  if (readiness.kind === "ready" || readiness.kind === "disabled") {
    return <>{children ?? null}</>;
  }

  // Use existing palette tokens; final color choice is a Don decision.
  const dotColor =
    readiness.kind === "not_ready" ? "bg-aether-warn" : "bg-aether-muted";

  if (children) {
    return (
      <span className="relative inline-block">
        {children}
        <span
          className={`absolute top-0 right-0 inline-block h-2 w-2 rounded-full ${dotColor}`}
          aria-label="retrieval not ready"
          title="Retrieval is not active — open the Trust drawer Retrieval tab for details"
        />
      </span>
    );
  }

  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${dotColor}`}
      aria-label="retrieval status indicator"
    />
  );
}
