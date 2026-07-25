"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { SelectableCard } from "@/components/ui/Card";
import { ARCHETYPES } from "@/lib/personas";
import { useWizardStore } from "@/lib/stores/wizard";
import { WizardStepId } from "@/lib/types";
import { WizardStepShell } from "./WizardStepShell";

export function StepPersonality() {
  const router = useRouter();
  const stored = useWizardStore((s) => s.selectedArchetype);
  const lastError = useWizardStore((s) => s.lastError);
  const submitStep = useWizardStore((s) => s.submitStep);
  const [selected, setSelected] = useState<string | null>(stored);
  const [busy, setBusy] = useState(false);

  const handleContinue = async (): Promise<void> => {
    if (!selected) return;
    setBusy(true);
    try {
      const result = await submitStep(WizardStepId.PERSONALITY, {
        selected_archetype: selected,
      });
      if (result.success) router.push("/onboarding/4-name/");
    } finally {
      setBusy(false);
    }
  };

  return (
    <WizardStepShell
      step={WizardStepId.PERSONALITY}
      title="Pick a personality."
      subtitle="The avatar is how they look. This is how they'll think and talk to you."
      footer={
        <>
          <Button variant="ghost" onClick={() => router.push("/onboarding/2-avatar/")}>
            ← Back
          </Button>
          <Button size="lg" onClick={handleContinue} disabled={!selected} isLoading={busy}>
            Continue
          </Button>
        </>
      }
    >
      {lastError && (
        <div
          role="alert"
          className="mb-4 px-4 py-2 rounded-md border border-error/50 bg-error/10 text-error text-[12px]"
        >
          {lastError}
        </div>
      )}
      <div
        role="radiogroup"
        aria-label="Choose a personality"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
      >
        {ARCHETYPES.map((a) => (
          <SelectableCard
            key={a.id}
            selected={selected === a.id}
            onClick={() => setSelected(a.id)}
            className="p-5"
          >
            <div className="text-[14px] font-medium text-fg-primary">{a.label}</div>
            <div className="text-[12px] text-fg-muted mt-1">{a.blurb}</div>
            <ul className="mt-4 space-y-1.5">
              {a.samples.map((sample, i) => (
                <li
                  key={i}
                  className="text-[12px] text-fg-secondary leading-5 italic border-l-2 border-border-subtle pl-3"
                >
                  “{sample}”
                </li>
              ))}
            </ul>
          </SelectableCard>
        ))}
      </div>
    </WizardStepShell>
  );
}
