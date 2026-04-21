interface Props {
  cues: string[];
  onPick: (cue: string) => void;
}

/**
 * Tiny horizontal strip of recent cues. Clicking a chip repopulates
 * the parent's cue input — the user can still edit before submitting.
 * Hidden when the history is empty.
 */
export function CueHistoryStrip({ cues, onPick }: Props) {
  if (cues.length === 0) return null;
  return (
    <div className="mt-2">
      <div className="text-[10.5px] uppercase tracking-[0.18em] text-aether-dim">
        Recent cues
      </div>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {cues.map((cue) => (
          <button
            key={cue}
            type="button"
            onClick={() => onPick(cue)}
            title={cue}
            className="max-w-[18rem] truncate rounded-full border border-aether-border bg-aether-elevated/60 px-2.5 py-0.5 text-[11px] text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
          >
            {cue}
          </button>
        ))}
      </div>
    </div>
  );
}
