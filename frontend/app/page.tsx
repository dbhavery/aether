"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Routing gate. Static export can't redirect server-side, so we render a
 * tiny placeholder and push on the client as soon as the bootstrap probe
 * has decided whether onboarding is needed.
 *
 * The probe runs locally rather than going through the session store so a
 * slow or down backend never traps the user on this page — we always fall
 * through to the wizard within PROBE_TIMEOUT_MS, on the assumption that a
 * user landing on `/` with no backend reachable is most likely a fresh
 * install with onboarding still pending.
 */
const HEALTH_URL = "http://localhost:8767/health";
const PROBE_TIMEOUT_MS = 2_000;

async function probeOnboardingComplete(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
    const resp = await fetch(HEALTH_URL, {
      signal: controller.signal,
      cache: "no-store",
    });
    clearTimeout(timer);
    if (!resp.ok) return false;
    const payload: unknown = await resp.json();
    return extractOnboardingFlag(payload);
  } catch {
    return false;
  }
}

function extractOnboardingFlag(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") return false;
  const p = payload as Record<string, unknown>;
  if (typeof p.onboarding_complete === "boolean") return p.onboarding_complete;
  const config = p.config;
  if (config && typeof config === "object") {
    const c = config as Record<string, unknown>;
    if (typeof c.onboarding_complete === "boolean") return c.onboarding_complete;
  }
  return false;
}

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const onboarded = await probeOnboardingComplete();
      if (cancelled) return;
      router.replace(onboarded ? "/chat/" : "/onboarding/1-welcome/");
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

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
