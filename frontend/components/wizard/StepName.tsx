"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { findPersona } from "@/lib/personas";
import { useWizardStore } from "@/lib/stores/wizard";
import { WizardStepId } from "@/lib/types";
import { WizardStepShell } from "./WizardStepShell";

const MAX_LEN = 40;
// v1.0 constraint from ONBOARDING-SPEC §2 Screen 4 — no HTML, markdown, or emoji.
const FORBIDDEN = /[<>`*_~|\[\]{}()#@\\/]|[\p{Extended_Pictographic}]/u;

export function StepName() {
  const router = useRouter();
  const selectedAvatarId = useWizardStore((s) => s.selectedAvatarId);
  const storedName = useWizardStore((s) => s.displayName);
  const submitStep = useWizardStore((s) => s.submitStep);

  const defaultName = useMemo(() => {
    const persona = selectedAvatarId ? findPersona(selectedAvatarId) : undefined;
    return persona?.displayName ?? "Aurora";
  }, [selectedAvatarId]);

  const [value, setValue] = useState<string>(storedName ?? defaultName);
  const [busy, setBusy] = useState(false);

  const trimmed = value.trim();
  const error: string | null = (() => {
    if (!trimmed) return "Name is required.";
    if (trimmed.length > MAX_LEN) return `Keep it to ${MAX_LEN} characters or fewer.`;
    if (FORBIDDEN.test(trimmed)) return "No HTML, markdown, or emoji in v1.0 (we'll revisit later).";
    return null;
  })();

  const handleContinue = async (): Promise<void> => {
    if (error) return;
    setBusy(true);
    try {
      const result = await submitStep(WizardStepId.NAME, { display_name: trimmed });
      if (result.success) router.push("/onboarding/5-llm/");
    } finally {
      setBusy(false);
    }
  };

  return (
    <WizardStepShell
      step={WizardStepId.NAME}
      title="What will you call them?"
      subtitle="Most people keep the default. You can change this any time."
      footer={
        <>
          <Button variant="ghost" onClick={() => router.push("/onboarding/3-personality/")}>
            ← Back
          </Button>
          <Button size="lg" onClick={handleContinue} disabled={!!error} isLoading={busy}>
            Continue
          </Button>
        </>
      }
    >
      <div className="max-w-md">
        <label
          htmlFor="display-name"
          className="block text-[12px] uppercase tracking-[0.14em] text-fg-muted mb-2"
        >
          Display name
        </label>
        <Input
          id="display-name"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          maxLength={MAX_LEN + 8}
          invalid={!!error && value.length > 0}
          autoFocus
          autoComplete="off"
          spellCheck={false}
          placeholder={defaultName}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !error) void handleContinue();
          }}
        />
        <div className="mt-2 flex items-center justify-between text-[11px] text-fg-muted">
          <span>{error ?? " "}</span>
          <span>
            {trimmed.length}/{MAX_LEN}
          </span>
        </div>
        <div className="mt-6 text-[13px] text-fg-secondary">
          Your assistant:{" "}
          <span className="text-fg-primary font-medium">
            {trimmed || defaultName}
          </span>
        </div>
      </div>
    </WizardStepShell>
  );
}
