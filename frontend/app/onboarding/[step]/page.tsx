import { notFound } from "next/navigation";
import { WIZARD_STEP_ORDER, WizardStepId, isWizardStepId } from "@/lib/types";
import { StepWelcome } from "@/components/wizard/StepWelcome";
import { StepAvatar } from "@/components/wizard/StepAvatar";
import { StepPersonality } from "@/components/wizard/StepPersonality";
import { StepName } from "@/components/wizard/StepName";
import { StepLlm } from "@/components/wizard/StepLlm";
import { StepVoice } from "@/components/wizard/StepVoice";
import { StepTerms } from "@/components/wizard/StepTerms";
import { StepHandoff } from "@/components/wizard/StepHandoff";

/**
 * Single dynamic route rendering every wizard screen by slug. Using one
 * route keeps shared shell / animation / error boundaries trivial, and the
 * explicit switch keeps us honest about the finite set of step IDs.
 */

// Required for `output: 'export'` — must enumerate every slug.
export function generateStaticParams(): { step: string }[] {
  return WIZARD_STEP_ORDER.map((step) => ({ step }));
}

// Disallow any other values so `/onboarding/foo` 404s statically.
export const dynamicParams = false;

interface PageProps {
  params: Promise<{ step: string }>;
}

export default async function WizardStepPage({ params }: PageProps) {
  const { step } = await params;
  if (!isWizardStepId(step)) {
    notFound();
  }

  switch (step) {
    case WizardStepId.WELCOME:
      return <StepWelcome />;
    case WizardStepId.AVATAR:
      return <StepAvatar />;
    case WizardStepId.PERSONALITY:
      return <StepPersonality />;
    case WizardStepId.NAME:
      return <StepName />;
    case WizardStepId.LLM:
      return <StepLlm />;
    case WizardStepId.VOICE:
      return <StepVoice />;
    case WizardStepId.TERMS:
      return <StepTerms />;
    case WizardStepId.HANDOFF:
      return <StepHandoff />;
    default: {
      // Exhaustiveness guard — TS error if we ever miss a case.
      const exhaustive: never = step;
      throw new Error(`Unhandled wizard step: ${exhaustive as string}`);
    }
  }
}
