"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { WIZARD_STEP_ORDER, WizardStepId } from "@/lib/types";

export interface WizardStepShellProps {
  step: WizardStepId;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * Shared frame for every wizard screen — consistent heading, progress strip,
 * and footer region. Each screen supplies its unique body + footer.
 */
export function WizardStepShell({ step, title, subtitle, children, footer }: WizardStepShellProps) {
  const stepIndex = WIZARD_STEP_ORDER.indexOf(step);
  // Exclude the handoff terminal step from the visible count (1..7).
  const displayIndex = stepIndex >= 0 ? stepIndex + 1 : 1;

  return (
    <motion.section
      key={step}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      className="w-full"
      aria-labelledby="wizard-title"
    >
      <ProgressStrip currentIndex={stepIndex} />
      <div className="mt-10 mb-3 text-[11px] uppercase tracking-[0.18em] text-fg-muted">
        Step {displayIndex} of {WIZARD_STEP_ORDER.length - 1}
      </div>
      <h1 id="wizard-title" className="text-[28px] leading-tight font-medium tracking-tight text-fg-primary">
        {title}
      </h1>
      {subtitle && (
        <p className="mt-2 text-[14px] text-fg-secondary max-w-prose">{subtitle}</p>
      )}
      <div className="mt-8">{children}</div>
      {footer && <div className="mt-10 flex items-center justify-between gap-4">{footer}</div>}
    </motion.section>
  );
}

function ProgressStrip({ currentIndex }: { currentIndex: number }) {
  // Exclude HANDOFF (last) from the visible bar — it's a terminal finalization
  // screen, not a user input step.
  const visibleSteps = WIZARD_STEP_ORDER.slice(0, WIZARD_STEP_ORDER.length - 1);
  return (
    <div className="flex gap-1" aria-hidden>
      {visibleSteps.map((stepId, idx) => {
        const state =
          idx < currentIndex ? "done" : idx === currentIndex ? "current" : "pending";
        const bgClass =
          state === "done"
            ? "bg-accent"
            : state === "current"
              ? "bg-accent/60"
              : "bg-bg-3";
        return (
          <span
            key={stepId}
            className={`h-0.5 flex-1 rounded-full transition-colors duration-300 ${bgClass}`}
          />
        );
      })}
    </div>
  );
}
