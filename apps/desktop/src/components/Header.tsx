import type {
  CompanionBanner,
  PersonaCatalogEntry,
  PresencePayload,
} from "../lib/types";
import { PresenceDot } from "./PresenceDot";
import { ProviderBadge } from "./ProviderBadge";

interface Props {
  banner: CompanionBanner;
  presence: PresencePayload;
  personas: PersonaCatalogEntry[];
  onOpenMemory: () => void;
  onOpenTrust: () => void;
  onOpenSettings: () => void;
  onOpenCamera: () => void;
  onOpenScreen: () => void;
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
  onReopenDisclosure,
  onClearSession,
  onSwitchPersona,
}: Props) {
  return (
    <header className="flex items-center justify-between border-b border-aether-border bg-aether-bg/95 px-5 py-3 backdrop-blur">
      <div className="flex items-center gap-4">
        <div className="flex flex-col">
          <div className="text-[14px] font-medium tracking-tight text-aether-text">
            Aether
          </div>
          <div className="text-[10.5px] font-mono uppercase tracking-wider text-aether-dim">
            · {banner.persona_name}
          </div>
        </div>
        {personas.length > 1 && (
          <>
            <div className="h-5 w-px bg-aether-border" aria-hidden />
            <label className="flex items-center gap-2 text-[11px] text-aether-muted">
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
        <div className="h-5 w-px bg-aether-border" aria-hidden />
        <PresenceDot state={presence.state} detail={presence.detail} />
      </div>
      <div className="flex items-center gap-3">
        <ProviderBadge banner={banner} />
        <div className="h-5 w-px bg-aether-border" aria-hidden />
        <button
          type="button"
          onClick={onOpenMemory}
          className="rounded-md border border-transparent px-2.5 py-1 text-[11.5px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text"
          title="Inspect session memory"
        >
          Memory
        </button>
        <button
          type="button"
          onClick={onOpenTrust}
          className="rounded-md border border-transparent px-2.5 py-1 text-[11.5px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text"
          title="Review every decision Aether has made"
        >
          Trust
        </button>
        <button
          type="button"
          onClick={onOpenCamera}
          className="rounded-md border border-transparent px-2.5 py-1 text-[11.5px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text"
          title="Camera capture (preview + single-frame analysis)"
        >
          Camera
        </button>
        <button
          type="button"
          onClick={onOpenScreen}
          className="rounded-md border border-transparent px-2.5 py-1 text-[11.5px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text"
          title="Screen capture (single screenshot + analysis)"
        >
          Screen
        </button>
        <button
          type="button"
          onClick={onOpenSettings}
          className="rounded-md border border-transparent px-2.5 py-1 text-[11.5px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text"
          title="Local settings (media permissions, etc.)"
        >
          Settings
        </button>
        <button
          type="button"
          onClick={onClearSession}
          className="rounded-md border border-transparent px-2.5 py-1 text-[11.5px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text"
          title="Clear the current session"
        >
          New session
        </button>
        <button
          type="button"
          onClick={onReopenDisclosure}
          className="rounded-md border border-transparent px-2.5 py-1 text-[11.5px] text-aether-muted transition-colors hover:border-aether-border hover:text-aether-text"
          title="What does Aether do with my data?"
        >
          About
        </button>
      </div>
    </header>
  );
}
