"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/lib/stores/session";

/**
 * Routing gate. Static export can't redirect server-side, so we render a
 * tiny placeholder and push on the client as soon as the bootstrap probe
 * has decided whether onboarding is needed.
 */
export default function Home() {
  const router = useRouter();
  const ready = useSessionStore((s) => s.onboardingCheckPerformed);
  const onboarded = useSessionStore((s) => s.onboardingComplete);

  useEffect(() => {
    if (!ready) return;
    if (onboarded) {
      router.replace("/chat/");
    } else {
      router.replace("/onboarding/1-welcome/");
    }
  }, [ready, onboarded, router]);

  return (
    <div className="h-full w-full flex items-center justify-center text-fg-muted text-sm">
      <PulseDot />
      <span className="ml-3">Starting Aether…</span>
    </div>
  );
}

function PulseDot() {
  return <span className="w-2 h-2 rounded-full bg-accent animate-pulse" aria-hidden />;
}
