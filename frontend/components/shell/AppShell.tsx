"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { useSessionStore } from "@/lib/stores/session";
import { ConnectionBadge } from "./ConnectionBadge";
import { ModeSwitcher } from "./ModeSwitcher";

/**
 * Top-level shell. Runs the `bootstrap` side-effect once on mount, hides its
 * own chrome during the wizard (full-bleed experience), and renders the
 * route content below a minimal header everywhere else.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const bootstrap = useSessionStore((s) => s.bootstrap);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const isOnboarding = pathname?.startsWith("/onboarding") ?? false;
  const isVideo = pathname?.startsWith("/video") ?? false;

  if (isOnboarding) {
    return (
      <div className="min-h-screen flex flex-col">
        <WindowChrome minimal />
        <main className="flex-1 flex items-center justify-center px-6 py-12">
          <div className="w-full" style={{ maxWidth: "var(--wizard-max)" }}>
            {children}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <WindowChrome />
      <main className={isVideo ? "flex-1 overflow-hidden" : "flex-1 overflow-auto"}>
        {children}
      </main>
    </div>
  );
}

function WindowChrome({ minimal = false }: { minimal?: boolean }) {
  return (
    <header
      className="flex items-center justify-between gap-4 h-12 px-5 border-b border-border-subtle bg-bg-0/80 backdrop-blur-sm sticky top-0 z-20"
      aria-label="Window chrome"
    >
      <div className="flex items-center gap-2">
        <LogoMark />
        <span className="text-[13px] font-medium tracking-tight text-fg-secondary select-none">
          Aether
        </span>
      </div>
      <div className="flex items-center gap-3">
        {!minimal && <ModeSwitcher />}
        <ConnectionBadge />
      </div>
    </header>
  );
}

function LogoMark() {
  return (
    <div
      className="w-5 h-5 rounded-full"
      aria-hidden
      style={{
        background:
          "radial-gradient(60% 60% at 30% 30%, var(--accent) 0%, rgba(227,183,112,0) 70%), conic-gradient(from 180deg, #2a2a2a, #1a1a1a, #2a2a2a)",
        boxShadow: "var(--shadow-raised)",
      }}
    />
  );
}
