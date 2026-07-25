"use client";

import { useSessionStore } from "@/lib/stores/session";
import type { WsStatus } from "@/lib/types";

const STATUS_META: Record<WsStatus, { label: string; dot: string; textClass: string }> = {
  connected: { label: "Connected", dot: "bg-ok", textClass: "text-fg-secondary" },
  connecting: { label: "Connecting", dot: "bg-warn animate-pulse", textClass: "text-fg-muted" },
  disconnected: { label: "Offline", dot: "bg-fg-disabled", textClass: "text-fg-muted" },
  error: { label: "Link error", dot: "bg-error", textClass: "text-fg-muted" },
};

/**
 * Compact badge showing backend link health. Always visible so the user
 * knows whether their keystrokes are reaching anything.
 */
export function ConnectionBadge() {
  const status = useSessionStore((s) => s.wsStatus);
  const detail = useSessionStore((s) => s.wsStatusDetail);
  const meta = STATUS_META[status];
  return (
    <div
      className="flex items-center gap-2 px-2.5 py-1 rounded-md border border-border-subtle bg-bg-1"
      role="status"
      aria-live="polite"
      title={detail ? `${meta.label} — ${detail}` : meta.label}
    >
      <span className={`w-2 h-2 rounded-full ${meta.dot}`} aria-hidden />
      <span className={`text-[11px] tracking-wide ${meta.textClass}`}>{meta.label}</span>
    </div>
  );
}
