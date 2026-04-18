"use client";

import { useEffect, useState } from "react";
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
  const setOnboardingComplete = useSessionStore((s) => s.setOnboardingComplete);
  const [doneIdx, setDoneIdx] = useState(0);

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

  return (
    <WizardStepShell
      step={WizardStepId.HANDOFF}
      title="Setting things up."
      subtitle="One moment. We'll drop you into the chat as soon as everything's ready."
    >
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
