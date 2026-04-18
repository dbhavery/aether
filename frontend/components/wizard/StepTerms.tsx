"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Modal } from "@/components/ui/Modal";
import { useWizardStore } from "@/lib/stores/wizard";
import { WizardStepId } from "@/lib/types";
import { WizardStepShell } from "./WizardStepShell";

type ModalKind = "terms" | "privacy" | null;

export function StepTerms() {
  const router = useRouter();
  const storedTelemetry = useWizardStore((s) => s.telemetry);
  const submitStep = useWizardStore((s) => s.submitStep);

  const [agreed, setAgreed] = useState(false);
  const [crash, setCrash] = useState(storedTelemetry.crash_reports);
  const [usage, setUsage] = useState(storedTelemetry.usage_counters);
  const [modal, setModal] = useState<ModalKind>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFinish = async (): Promise<void> => {
    if (!agreed) {
      setError("You need to accept the Terms to continue.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const result = await submitStep(WizardStepId.TERMS, {
        accepted_terms_at: new Date().toISOString(),
        telemetry: { crash_reports: crash, usage_counters: usage },
      });
      if (result.success) router.push("/onboarding/8-handoff/");
      else if (result.error) setError(result.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <WizardStepShell
      step={WizardStepId.TERMS}
      title="A few plain rules."
      subtitle="Short, honest, opt-in telemetry — off by default."
      footer={
        <>
          <Button variant="ghost" onClick={() => router.push("/onboarding/6-voice/")}>
            ← Back
          </Button>
          <Button size="lg" onClick={handleFinish} disabled={!agreed} isLoading={busy}>
            Finish setup
          </Button>
        </>
      }
    >
      {error && (
        <div
          role="alert"
          className="mb-4 px-4 py-2 rounded-md border border-error/50 bg-error/10 text-error text-[12px]"
        >
          {error}
        </div>
      )}
      <div className="space-y-5 max-w-xl">
        <ul className="text-[13px] text-fg-secondary space-y-2 leading-6">
          <li>• Aether runs on your machine. Your conversations don't leave unless you configured a cloud model or voice yourself.</li>
          <li>• We don't collect any data by default.</li>
          <li>• You are responsible for how you use AI outputs.</li>
        </ul>

        <div
          className="p-5 rounded-[var(--radius-md)] bg-bg-2 border border-border-subtle space-y-4"
          style={{ boxShadow: "var(--shadow-raised)" }}
        >
          <Checkbox
            checked={crash}
            onChange={setCrash}
            description="Send anonymous crash reports. Off by default."
          >
            Help us fix crashes
          </Checkbox>
          <Checkbox
            checked={usage}
            onChange={setUsage}
            description="Send anonymous usage counters (step counts, mode toggles). No content, ever."
          >
            Share anonymous usage counters
          </Checkbox>
        </div>

        <div className="flex flex-wrap gap-3 text-[12px]">
          <button
            type="button"
            className="text-fg-muted hover:text-accent underline-offset-4 hover:underline"
            onClick={() => setModal("terms")}
          >
            Read full Terms
          </button>
          <span className="text-fg-muted">•</span>
          <button
            type="button"
            className="text-fg-muted hover:text-accent underline-offset-4 hover:underline"
            onClick={() => setModal("privacy")}
          >
            Read full Privacy Policy
          </button>
        </div>

        <div
          className="p-4 rounded-[var(--radius-md)] border border-border-default"
          style={{ background: "var(--bg-1)" }}
        >
          <Checkbox checked={agreed} onChange={setAgreed}>
            I agree to the Terms of Service and Privacy Policy.
          </Checkbox>
        </div>
      </div>

      <Modal open={modal === "terms"} onClose={() => setModal(null)} title="Terms of Service">
        <TermsText />
      </Modal>
      <Modal open={modal === "privacy"} onClose={() => setModal(null)} title="Privacy Policy">
        <PrivacyText />
      </Modal>
    </WizardStepShell>
  );
}

function TermsText() {
  return (
    <div className="space-y-3">
      <p>
        Aether is offered under the MIT license. You may use, copy, modify, and redistribute it,
        subject to the copyright notice and disclaimer in the LICENSE file.
      </p>
      <p>
        You are solely responsible for the prompts you submit and the outputs you act on. Aether
        is a tool; it may produce incorrect or incomplete information. Don't rely on it for
        medical, legal, or financial decisions without independent verification.
      </p>
      <p>
        When you configure a cloud model or voice provider, their terms apply to the traffic
        routed through them. We never read or store your API keys — they live in your OS
        keyring.
      </p>
      <p className="text-fg-muted text-[12px]">
        Full text will be finalized in TERMS.md before v1.0 ships.
      </p>
    </div>
  );
}

function PrivacyText() {
  return (
    <div className="space-y-3">
      <p>
        Aether collects no data by default. Conversations, transcripts, and embeddings stay on
        your machine.
      </p>
      <p>
        If you opt in to anonymous crash reports, we receive a stack trace, Aether version, and
        your opaque installation id. We never receive your prompts, responses, keys, or persona
        choices.
      </p>
      <p>
        If you opt in to anonymous usage counters, we receive step-count and mode-toggle
        aggregates keyed on the same installation id. Again, no content of any kind.
      </p>
      <p className="text-fg-muted text-[12px]">
        Full text will be finalized in PRIVACY.md before v1.0 ships.
      </p>
    </div>
  );
}
