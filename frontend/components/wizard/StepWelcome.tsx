"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useWizardStore } from "@/lib/stores/wizard";
import { WizardStepId } from "@/lib/types";
import { WizardStepShell } from "./WizardStepShell";

export function StepWelcome() {
  const router = useRouter();
  const submitStep = useWizardStore((s) => s.submitStep);
  const [busy, setBusy] = useState(false);

  const handleStart = async (): Promise<void> => {
    setBusy(true);
    try {
      const result = await submitStep(WizardStepId.WELCOME, {
        started_at: new Date().toISOString(),
      });
      if (result.success) {
        router.push("/onboarding/2-avatar/");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <WizardStepShell
      step={WizardStepId.WELCOME}
      title="Meet your AI companion."
      subtitle="Aether runs on your computer. Private. Yours. Choose who you want to talk to."
      footer={
        <div className="flex-1 flex justify-end">
          <Button size="lg" onClick={handleStart} isLoading={busy}>
            Get started
          </Button>
        </div>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
        <ValueCard
          title="Private"
          detail="Everything runs locally unless you explicitly pick a cloud model or voice."
        />
        <ValueCard
          title="Flexible"
          detail="Pick any LLM — local, hosted, or try it out with our free Guest mode."
        />
        <ValueCard
          title="Real"
          detail="Expressive voice and lip-synced avatar, right on your machine."
        />
      </div>
    </WizardStepShell>
  );
}

function ValueCard({ title, detail }: { title: string; detail: string }) {
  return (
    <div
      className="p-4 rounded-[var(--radius-md)] bg-bg-2 border border-border-subtle"
      style={{ boxShadow: "var(--shadow-raised)" }}
    >
      <div className="text-[12px] uppercase tracking-[0.16em] text-accent/90">{title}</div>
      <p className="mt-2 text-[13px] text-fg-secondary leading-5">{detail}</p>
    </div>
  );
}
