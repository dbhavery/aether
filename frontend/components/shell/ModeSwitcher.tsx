"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const MODES = [
  { id: "chat", label: "Chat", href: "/chat/" },
  { id: "sandbox", label: "Sandbox", href: "/sandbox/" },
  { id: "video", label: "Video", href: "/video/" },
] as const;

/**
 * Segmented control that navigates between the three product modes.
 * Highlights the current mode based on pathname — the URL is the single
 * source of truth so back/forward keep the pill in sync.
 */
export function ModeSwitcher() {
  const pathname = usePathname() ?? "";
  return (
    <div
      className="flex items-center p-0.5 rounded-lg border border-border-subtle bg-bg-1"
      role="tablist"
      aria-label="Interaction mode"
    >
      {MODES.map((m) => {
        const active = pathname.startsWith(m.href) || pathname.startsWith(m.href.slice(0, -1));
        return (
          <Link
            key={m.id}
            href={m.href}
            role="tab"
            aria-selected={active}
            className={`px-3 py-1 text-[12px] rounded-md transition-colors duration-150 ${
              active
                ? "bg-bg-3 text-fg-primary shadow-[var(--shadow-raised)]"
                : "text-fg-muted hover:text-fg-secondary"
            }`}
          >
            {m.label}
          </Link>
        );
      })}
    </div>
  );
}
