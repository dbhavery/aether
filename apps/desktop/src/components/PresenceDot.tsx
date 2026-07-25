import type { PresenceStateLabel } from "../lib/types";

interface Props {
  state: PresenceStateLabel;
  detail?: string | null;
}

const STATE_META: Record<
  PresenceStateLabel,
  { color: string; label: string; animated: boolean }
> = {
  quiet: { color: "bg-aether-dim", label: "quiet", animated: false },
  listening: { color: "bg-aether-accent", label: "listening", animated: true },
  thinking: { color: "bg-aether-accent", label: "thinking", animated: true },
  "awaiting-approval": {
    color: "bg-aether-warn",
    label: "awaiting approval",
    animated: true,
  },
  responding: { color: "bg-aether-ok", label: "responding", animated: true },
};

export function PresenceDot({ state, detail }: Props) {
  const meta = STATE_META[state];
  return (
    <div className="flex items-center gap-2 text-xs text-aether-muted">
      <span
        className={`inline-block h-2 w-2 rounded-full ${meta.color} ${
          meta.animated ? "animate-pulseDot" : ""
        }`}
        aria-hidden
      />
      <span className="tracking-wide">{meta.label}</span>
      {detail && (
        <span className="text-aether-dim font-mono text-[11px]">· {detail}</span>
      )}
    </div>
  );
}
