import type { CompanionBanner, PresencePayload } from "../lib/types";
import { PresenceDot } from "./PresenceDot";
import { ProviderBadge } from "./ProviderBadge";

interface Props {
  banner: CompanionBanner;
  presence: PresencePayload;
  onOpenMemory: () => void;
  onReopenDisclosure: () => void;
  onClearSession: () => void;
}

export function Header({
  banner,
  presence,
  onOpenMemory,
  onReopenDisclosure,
  onClearSession,
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
