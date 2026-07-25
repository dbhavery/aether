import type {
  CompanionBanner,
  PersonaCatalogEntry,
  PresencePayload,
} from "../lib/types";
import { PresenceDot } from "./PresenceDot";
import { ProviderBadge } from "./ProviderBadge";
import { ReadinessIndicator } from "./ReadinessIndicator";

interface Props {
  banner: CompanionBanner;
  presence: PresencePayload;
  personas: PersonaCatalogEntry[];
  onOpenMemory: () => void;
  onOpenTrust: () => void;
  onOpenSettings: () => void;
  onOpenCamera: () => void;
  onOpenScreen: () => void;
  onOpenVoice: () => void;
  onReopenDisclosure: () => void;
  onClearSession: () => void;
  onSwitchPersona: (id: string) => void;
}

export function Header({
  banner,
  presence,
  personas,
  onOpenMemory,
  onOpenTrust,
  onOpenSettings,
  onOpenCamera,
  onOpenScreen,
  onOpenVoice,
  onReopenDisclosure,
  onClearSession,
  onSwitchPersona,
}: Props) {
  return (
    // Responsive breakpoint at 1024 px (Tailwind `lg:`) collapses the
    // header chrome to keep it on one line at the dev build's default
    // 976 px window width. Phase 6 UX audit Bug 5.1 documented the
    // pre-fix state: route badge wrapped to 3 lines, presence label
    // clipped. Below the breakpoint we drop label gaps, shorten button
    // padding, hide the persona select (still reachable via Settings),
    // and shrink the provider badge — every chip stays single-line at
    // 976 px and remains identical at >=1024 px. `flex-nowrap` +
    // `min-w-0` propagate the shrink permission down to truncatable
    // children (the provider label).
    <header
      data-testid="app-header"
      className="flex flex-nowrap items-center justify-between gap-2 border-b border-aether-border bg-aether-bg/95 px-3 py-2 backdrop-blur lg:gap-3 lg:px-5 lg:py-3"
    >
      <div className="flex min-w-0 flex-nowrap items-center gap-2 lg:gap-4">
        <div className="flex shrink-0 flex-col">
          <div className="text-[13px] font-medium tracking-tight text-aether-text lg:text-[14px]">
            Companion
          </div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-aether-dim lg:text-[10.5px]">
            · {banner.persona_name}
          </div>
        </div>
        {personas.length > 1 && (
          <>
            <div className="hidden h-5 w-px bg-aether-border lg:block" aria-hidden />
            <label className="hidden items-center gap-2 text-[11px] text-aether-muted lg:flex">
              <span className="hidden sm:inline">Persona</span>
              <select
                value={banner.persona_id}
                onChange={(e) => onSwitchPersona(e.target.value)}
                className="rounded-md border border-aether-border bg-aether-elevated px-2 py-1 text-[11.5px] text-aether-text focus:outline-none focus:ring-1 focus:ring-aether-accent"
                title="Switch active persona (clears session)"
              >
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.stance}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <div className="hidden h-5 w-px shrink-0 bg-aether-border sm:block" aria-hidden />
        <div className="min-w-0 shrink">
          <PresenceDot state={presence.state} detail={presence.detail} />
        </div>
      </div>
      <div className="flex shrink-0 flex-nowrap items-center gap-1.5 lg:gap-3">
        <div className="hidden max-w-[180px] sm:block">
          <ProviderBadge banner={banner} />
        </div>
        <div className="hidden h-5 w-px bg-aether-border lg:block" aria-hidden />
        <button
          type="button"
          onClick={onOpenMemory}
          className="rounded-md border border-transparent px-2 py-1 text-[11px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text lg:px-2.5 lg:text-[11.5px]"
          title="Inspect session memory"
        >
          Memory
        </button>
        <ReadinessIndicator>
          <button
            type="button"
            onClick={onOpenTrust}
            className="rounded-md border border-transparent px-2 py-1 text-[11px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text lg:px-2.5 lg:text-[11.5px]"
            title="Review every decision Companion has made"
          >
            Trust
          </button>
        </ReadinessIndicator>
        <button
          type="button"
          onClick={onOpenCamera}
          className="rounded-md border border-transparent px-2 py-1 text-[11px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text lg:px-2.5 lg:text-[11.5px]"
          title="Camera capture (preview + single-frame analysis)"
        >
          Camera
        </button>
        <button
          type="button"
          onClick={onOpenScreen}
          className="rounded-md border border-transparent px-2 py-1 text-[11px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text lg:px-2.5 lg:text-[11.5px]"
          title="Screen capture (single screenshot + analysis)"
        >
          Screen
        </button>
        <button
          type="button"
          onClick={onOpenVoice}
          className="rounded-md border border-transparent px-2 py-1 text-[11px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text lg:px-2.5 lg:text-[11.5px]"
          title="Voice capture (push-to-talk, single utterance)"
        >
          Voice
        </button>
        <button
          type="button"
          onClick={onOpenSettings}
          className="rounded-md border border-transparent px-2 py-1 text-[11px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text lg:px-2.5 lg:text-[11.5px]"
          title="Local settings (media permissions, etc.)"
        >
          Settings
        </button>
        <button
          type="button"
          onClick={onClearSession}
          className="rounded-md border border-transparent px-2 py-1 text-[11px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text lg:px-2.5 lg:text-[11.5px]"
          title="Clear the current session"
        >
          New session
        </button>
        <button
          type="button"
          onClick={onReopenDisclosure}
          className="hidden rounded-md border border-transparent px-2 py-1 text-[11px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text lg:inline-block lg:px-2.5 lg:text-[11.5px]"
          title="What does Companion do with my data?"
        >
          About
        </button>
      </div>
    </header>
  );
}
