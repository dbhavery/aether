import { useEffect, useState } from "react";

/**
 * Generic transient toast component (ADR-0007 D6 surface).
 *
 * Single-purpose: render one message that auto-dismisses after
 * `durationMs`. Stacking, deduplication, and emission rules live in
 * `ToastContainer`.
 *
 * Visual contract is intentionally minimal — uses existing aether
 * color tokens, fixed bottom-right placement, no animation library
 * dependency. Don's taste call to refine if needed.
 */

export type ToastTone = "info" | "ok" | "warn" | "err";

interface Props {
  id: string;
  message: string;
  tone: ToastTone;
  durationMs?: number;
  onDismiss: (id: string) => void;
}

const TONE_CLASSES: Record<ToastTone, string> = {
  info: "border-aether-border bg-aether-bg/90 text-aether-text",
  ok: "border-aether-ok/40 bg-aether-bg/90 text-aether-ok",
  warn: "border-aether-warn/40 bg-aether-bg/90 text-aether-warn",
  err: "border-aether-err/40 bg-aether-bg/90 text-aether-err",
};

export function Toast({ id, message, tone, durationMs = 4000, onDismiss }: Props) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => {
      setVisible(false);
      // Wait for the fade-out frame before removing from the parent.
      setTimeout(() => onDismiss(id), 180);
    }, durationMs);
    return () => clearTimeout(t);
  }, [id, durationMs, onDismiss]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={`pointer-events-auto rounded-md border px-3 py-2 text-[12px] shadow-lg transition-opacity ${
        TONE_CLASSES[tone]
      } ${visible ? "opacity-100" : "opacity-0"}`}
    >
      {message}
    </div>
  );
}
