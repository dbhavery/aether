import { useEffect, useRef, useState } from "react";

import {
  embeddingsReadiness,
  onBackfillDone,
} from "../lib/api";
import type { ReadinessState } from "../lib/types";
import { Toast, type ToastTone } from "./Toast";

/**
 * Global toast surface for ADR-0007 D6.
 *
 * Mounted once at the App root. Subscribes to:
 *   - Retrieval readiness transitions (poll every 5s; compare to
 *     last-known state; emit toast on change). Polling rather than
 *     event-driven keeps the wiring local — the readiness state
 *     machine doesn't need an AppHandle plumbed through.
 *   - Backfill completion via the existing `backfill:done` event.
 *
 * Toast emission rules (research-backed badges-for-state /
 * toasts-for-events split):
 *   - Steady state (kind unchanged across two polls) → no toast.
 *   - ready → not_ready → "Retrieval went offline" warn toast so the
 *     user knows their last turn degraded.
 *   - not_ready → ready → "Retrieval is back" ok toast.
 *   - disabled / unknown transitions are silent (intentional state).
 *   - Backfill done → ok toast with completion summary.
 *
 * Visual decisions Don may want to refine:
 *   - Position (currently fixed bottom-right).
 *   - Duration (4 sec default per Toast component).
 *   - Stack ordering (currently newest-on-top).
 *   - Whether to merge rapid same-kind toasts (currently no dedupe).
 */

const POLL_INTERVAL_MS = 5_000;

interface ToastEntry {
  id: string;
  message: string;
  tone: ToastTone;
}

function readinessKindLabel(state: ReadinessState): string {
  return state.kind;
}

function transitionMessage(
  from: ReadinessState,
  to: ReadinessState,
): { tone: ToastTone; message: string } | null {
  // Silent transitions: intentional off-states don't warrant a toast.
  if (from.kind === "unknown" || to.kind === "unknown") return null;
  if (from.kind === to.kind) return null;
  if (to.kind === "disabled" || from.kind === "disabled") return null;

  if (to.kind === "not_ready") {
    return {
      tone: "warn",
      message: "Retrieval went offline. Recent turns ran without context.",
    };
  }
  if (to.kind === "ready" && from.kind === "not_ready") {
    return { tone: "ok", message: "Retrieval is back. Context is active again." };
  }
  return null;
}

let nextToastId = 0;

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const lastReadinessRef = useRef<ReadinessState | null>(null);

  useEffect(() => {
    let mounted = true;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    const unsubs: Array<() => void> = [];

    function emit(message: string, tone: ToastTone) {
      const id = `t-${nextToastId++}`;
      setToasts((cur) => [{ id, message, tone }, ...cur].slice(0, 5));
    }

    async function pollReadiness() {
      try {
        const cur = await embeddingsReadiness();
        if (!mounted) return;
        const prev = lastReadinessRef.current;
        if (prev && readinessKindLabel(prev) !== readinessKindLabel(cur)) {
          const transition = transitionMessage(prev, cur);
          if (transition) emit(transition.message, transition.tone);
        }
        lastReadinessRef.current = cur;
      } catch {
        // Silent — toast surface should never throw.
      }
    }

    void pollReadiness();
    pollTimer = setInterval(pollReadiness, POLL_INTERVAL_MS);

    onBackfillDone((payload) => {
      if (!mounted) return;
      if (payload.cancelled) {
        emit(
          `Backfill cancelled at ${payload.completed} of ${payload.total} memories.`,
          "info",
        );
      } else if (payload.failures > 0) {
        // Phase 3B F2: hard failures get the warn tone and a re-run
        // hint. The user has to decide whether to retry, so the toast
        // says so explicitly.
        emit(
          `Backfill complete — ${payload.completed} indexed, ${payload.failures} failed. Re-run to retry.`,
          "warn",
        );
      } else if (payload.recovered_failures > 0 && payload.completed > 0) {
        // Phase 3B F2: zero hard failures + non-zero recovered means
        // the retry loop did its job. Stay on the ok tone so the user
        // understands the system self-healed; the parenthetical names
        // the recovery so it isn't a silent surprise.
        emit(
          `Backfill complete — ${payload.completed} indexed (${payload.recovered_failures} transient ${payload.recovered_failures === 1 ? "error" : "errors"} recovered).`,
          "ok",
        );
      } else if (payload.completed > 0) {
        emit(`Backfill complete — ${payload.completed} memories indexed.`, "ok");
      }
    }).then((off) => unsubs.push(off));

    return () => {
      mounted = false;
      if (pollTimer) clearInterval(pollTimer);
      unsubs.forEach((fn) => fn());
    };
  }, []);

  function handleDismiss(id: string) {
    setToasts((cur) => cur.filter((t) => t.id !== id));
  }

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <Toast
          key={t.id}
          id={t.id}
          message={t.message}
          tone={t.tone}
          onDismiss={handleDismiss}
        />
      ))}
    </div>
  );
}
