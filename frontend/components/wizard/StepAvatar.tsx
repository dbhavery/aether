"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { SelectableCard } from "@/components/ui/Card";
import { getWsClient } from "@/lib/ws";
import { ExtendedEventType, WizardStepId } from "@/lib/types";
import { PERSONAS } from "@/lib/personas";
import { useWizardStore } from "@/lib/stores/wizard";
import { PersonaPortrait } from "./PersonaPortrait";
import { WizardStepShell } from "./WizardStepShell";

export function StepAvatar() {
  const router = useRouter();
  const storedId = useWizardStore((s) => s.selectedAvatarId);
  const lastError = useWizardStore((s) => s.lastError);
  const submitStep = useWizardStore((s) => s.submitStep);
  const [selected, setSelected] = useState<string | null>(storedId);
  const [hovered, setHovered] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleContinue = async (): Promise<void> => {
    if (!selected) return;
    setBusy(true);
    try {
      const result = await submitStep(WizardStepId.AVATAR, { selected_avatar_id: selected });
      if (result.success) router.push("/onboarding/3-personality/");
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = (personaId: string): void => {
    // Fire-and-forget — backend is expected to play voice/sample.wav out of
    // the persona pack via its audio pipeline.
    getWsClient().send(ExtendedEventType.VOICE_PREVIEW_REQUEST, { persona_id: personaId });
  };

  return (
    <WizardStepShell
      step={WizardStepId.AVATAR}
      title="Pick an avatar."
      subtitle="You can change this any time. This is how they'll look — personality comes next."
      footer={
        <>
          <Button variant="ghost" onClick={() => router.push("/onboarding/1-welcome/")}>
            ← Back
          </Button>
          <Button size="lg" onClick={handleContinue} disabled={!selected} isLoading={busy}>
            Continue
          </Button>
        </>
      }
    >
      {lastError && <ErrorBanner message={lastError} />}
      <div
        role="radiogroup"
        aria-label="Choose an avatar"
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3"
      >
        {PERSONAS.map((p) => {
          const isSelected = selected === p.id;
          const isHovered = hovered === p.id;
          return (
            <SelectableCard
              key={p.id}
              selected={isSelected}
              onClick={() => setSelected(p.id)}
              onMouseEnter={() => setHovered(p.id)}
              onMouseLeave={() => setHovered((h) => (h === p.id ? null : h))}
              onFocus={() => setHovered(p.id)}
              onBlur={() => setHovered((h) => (h === p.id ? null : h))}
              aria-label={`${p.displayName}: ${p.tagline}`}
              className="p-4"
            >
              <div className="flex flex-col items-center text-center gap-3">
                <PersonaPortrait
                  id={p.id}
                  displayName={p.displayName}
                  hue={p.hue}
                  animated={isHovered || isSelected}
                />
                <div>
                  <div className="text-[14px] font-medium text-fg-primary">{p.displayName}</div>
                  <div className="text-[11px] text-fg-muted mt-1 leading-4 min-h-[2rem]">
                    {p.tagline}
                  </div>
                </div>
                <button
                  type="button"
                  className="text-[11px] text-fg-muted hover:text-accent tracking-wide"
                  onClick={(e) => {
                    e.stopPropagation();
                    handlePreview(p.id);
                  }}
                >
                  ▶ Preview voice
                </button>
              </div>
            </SelectableCard>
          );
        })}
      </div>
    </WizardStepShell>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="mb-4 px-4 py-2 rounded-md border border-error/50 bg-error/10 text-error text-[12px]"
    >
      {message}
    </div>
  );
}
