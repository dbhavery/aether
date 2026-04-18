"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getWsClient } from "@/lib/ws";
import { EventType, WizardStepId } from "@/lib/types";
import { useSessionStore } from "@/lib/stores/session";
import { useWizardStore } from "@/lib/stores/wizard";
import { WizardStepShell } from "./WizardStepShell";

const TASKS: readonly { id: string; label: string }[] = [
  { id: "config", label: "Writing configuration" },
  { id: "memory", label: "Preparing memory store" },
  { id: "avatar", label: "Waking the avatar engine" },
  { id: "voice", label: "Warming the voice model" },
  { id: "welcome", label: "Composing a hello message" },
];

/**
 * Terminal screen. We subscribe to ONBOARDING_COMPLETE and navigate to /chat
 * as soon as the backend finalizes. While waiting, render a reassuring
 * checklist that marches forward every ~700ms — this is purely cosmetic so
 * the user knows the app is alive.
 */
export function StepHandoff() {
  const router = useRouter();
  const resetWizard = useWizardStore((s) => s.resetAll);
  const submitStep = useWizardStore((s) => s.submitStep);
  const setOnboardingComplete = useSessionStore((s) => s.setOnboardingComplete);
  const [doneIdx, setDoneIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const submittedRef = useRef(false);

  useEffect(() => {
    if (doneIdx >= TASKS.length) return;
    const timer = setTimeout(() => {
      setDoneIdx((i) => Math.min(i + 1, TASKS.length));
    }, 700);
    return () => clearTimeout(timer);
  }, [doneIdx]);

  useEffect(() => {
    const ws = getWsClient();
    const unsub = ws.subscribe(EventType.ONBOARDING_COMPLETE, () => {
      setOnboardingComplete(true);
      resetWizard();
      router.replace("/chat/");
    });
    return unsub;
  }, [resetWizard, router, setOnboardingComplete]);

  // Fire the HANDOFF submit exactly once on mount. The backend re-validates
  // every prior step, calls finalize_wizard (writes config.yaml + sets
  // onboarding_complete=true), then sends WIZARD_STEP_RESULT and broadcasts
  // ONBOARDING_COMPLETE in that order. We redirect on the submit reply
  // because subscribing to ONBOARDING_COMPLETE alone is racy: the WS may
  // bounce between the reply and the broadcast and lose the one-shot event.
  // The ONBOARDING_COMPLETE subscriber above stays as a secondary trigger.
  // The HMR-safe ref guard keeps Strict Mode's double-invoke from sending
  // two submits.
  useEffect(() => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    void (async () => {
      const result = await submitStep(WizardStepId.HANDOFF, {});
      if (result.success) {
        setOnboardingComplete(true);
        resetWizard();
        router.replace("/chat/");
      } else {
        setError(result.error ?? "Could not finalize setup. Try again.");
        // Allow a retry by resetting the guard.
        submittedRef.current = false;
      }
    })();
  }, [submitStep, setOnboardingComplete, resetWizard, router]);

  return (
    <WizardStepShell
      step={WizardStepId.HANDOFF}
      title="Setting things up."
      subtitle="One moment. We'll drop you into the chat as soon as everything's ready."
    >
      {error && (
        <div
          role="alert"
          className="mb-4 px-4 py-2 rounded-md border border-error/50 bg-error/10 text-error text-[12px]"
        >
          {error}
        </div>
      )}
      <ol className="space-y-3 max-w-md">
        {TASKS.map((task, idx) => {
          const complete = idx < doneIdx;
          const active = idx === doneIdx;
          return (
            <li key={task.id} className="flex items-center gap-3 text-[13px]">
              <StatusDot state={complete ? "done" : active ? "active" : "pending"} />
              <span
                className={
                  complete
                    ? "text-fg-primary"
                    : active
                      ? "text-fg-secondary"
                      : "text-fg-muted"
                }
              >
                {task.label}
              </span>
            </li>
          );
        })}
      </ol>
    </WizardStepShell>
  );
}

function StatusDot({ state }: { state: "done" | "active" | "pending" }) {
  if (state === "done") {
    return (
      <span
        className="w-4 h-4 rounded-full bg-accent flex items-center justify-center shrink-0"
        aria-hidden
      >
        <svg width="9" height="9" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M2 5.2L4 7.4L8 2.6" stroke="#0a0a0a" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  }
  if (state === "active") {
    return (
      <span
        className="w-4 h-4 rounded-full border-2 border-accent border-r-transparent animate-spin shrink-0"
        aria-hidden
      />
    );
  }
  return <span className="w-4 h-4 rounded-full bg-bg-3 shrink-0" aria-hidden />;
}
