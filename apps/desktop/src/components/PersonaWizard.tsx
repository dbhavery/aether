import { useEffect, useMemo, useRef, useState } from "react";

import {
  loadPersonaPreviews,
  previewAssetUrl,
  type PersonaPreview,
} from "../lib/personaPreviews";

/**
 * Onboarding wizard — picks one of the 9 v0 cast personas before the
 * conversation UI is reachable. Reads the bundled Tier-1 previews
 * (preview.webp + preview_voice.opus + tagline/archetype yaml fields)
 * via `/personas-previews/index.json`. No network round-trip required.
 *
 * Per ADR-0012 §7, this is the first step in the onboarding flow:
 *   - Show 9 cards (thumb + name + tagline + archetype tag)
 *   - Hover/click a card → play that persona's 3-second voice clip
 *   - Click "Choose" on a card → move to confirmation step
 *   - Confirmation step → mocks the Tier-2 download until the L6
 *     install backend lands (coordinator-gated work)
 *
 * The "commit" handler is provided by the parent so this component
 * stays decoupled from the App's persistence + state machine.
 */
export interface PersonaWizardProps {
  /** Called when the user confirms a persona pick. */
  onCommit: (slug: string) => void;
}

type Step = "pick" | "confirm";

export function PersonaWizard({ onCommit }: PersonaWizardProps) {
  const [step, setStep] = useState<Step>("pick");
  const [personas, setPersonas] = useState<PersonaPreview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [playingSlug, setPlayingSlug] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadPersonaPreviews()
      .then((data) => {
        if (!cancelled) setPersonas(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err.message ?? String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(
    () =>
      selectedSlug && personas
        ? personas.find((p) => p.slug === selectedSlug) ?? null
        : null,
    [selectedSlug, personas],
  );

  function playPreview(p: PersonaPreview) {
    // Stop the previous clip cleanly so two cards can't overlap.
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    const audio = new Audio(previewAssetUrl(p.preview_voice_opus));
    audio.onended = () => {
      setPlayingSlug((cur) => (cur === p.slug ? null : cur));
    };
    audioRef.current = audio;
    setPlayingSlug(p.slug);
    void audio.play().catch(() => {
      // Autoplay can fail if the user hasn't interacted yet. Reset
      // the playing indicator so the UI doesn't lie.
      setPlayingSlug((cur) => (cur === p.slug ? null : cur));
    });
  }

  function selectPersona(p: PersonaPreview) {
    setSelectedSlug(p.slug);
    playPreview(p);
  }

  if (loadError) {
    return (
      <div
        role="alert"
        className="mx-auto mt-24 max-w-md rounded-lg border border-aether-border bg-aether-bg p-6 text-aether-text"
      >
        <h2 className="text-[15px] font-medium">Couldn't load companions</h2>
        <p className="mt-2 text-[13px] text-aether-muted">{loadError}</p>
        <p className="mt-4 text-[12px] text-aether-dim">
          The wizard expects a bundled persona preview index at
          /personas-previews/index.json. If this is a dev build, run:
          <code className="ml-1 font-mono text-aether-text">
            python tools/build-persona-previews/build.py
          </code>
        </p>
      </div>
    );
  }

  if (!personas) {
    return (
      <div className="mx-auto mt-24 max-w-md text-center text-[13px] text-aether-muted">
        Loading companions…
      </div>
    );
  }

  if (step === "confirm" && selected) {
    return (
      <div className="mx-auto mt-16 max-w-lg px-6">
        <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
          Confirm
        </div>
        <h1 className="mt-1 text-[20px] font-medium text-aether-text">
          You picked {selected.display_name}
        </h1>
        <p className="mt-3 text-[13px] leading-relaxed text-aether-muted">
          {selected.tagline}
        </p>
        <div className="mt-6 rounded-lg border border-aether-border bg-aether-elevated p-4">
          <p className="text-[12px] text-aether-muted">
            {selected.display_name}'s full pack (~10–13 MB) will download.
            Subsequent conversations stay offline.
          </p>
          <p className="mt-2 text-[11px] text-aether-dim">
            You can change companions later in Settings. Your conversation
            history and memory are preserved across switches.
          </p>
        </div>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            className="rounded-md border border-aether-border px-3 py-1.5 text-[12px] text-aether-muted hover:border-aether-text hover:text-aether-text"
            onClick={() => setStep("pick")}
          >
            Back
          </button>
          <button
            type="button"
            className="rounded-md border border-aether-accent bg-aether-accent/10 px-4 py-1.5 text-[12px] font-medium text-aether-accent hover:bg-aether-accent/20"
            onClick={() => onCommit(selected.slug)}
          >
            Continue with {selected.display_name.split(" ")[0]}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="text-center">
        <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
          Pick your companion
        </div>
        <h1 className="mt-2 text-[22px] font-medium text-aether-text">
          Nine companions, nine registers
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-[13px] leading-relaxed text-aether-muted">
          Each is a distinct character with their own voice, presence,
          and way of thinking. Tap a card to hear them speak. You'll
          stick with one — though you can switch later.
        </p>
      </div>

      <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {personas.map((p) => {
          const isSelected = selectedSlug === p.slug;
          const isPlaying = playingSlug === p.slug;
          return (
            <button
              key={p.slug}
              type="button"
              onClick={() => selectPersona(p)}
              aria-pressed={isSelected}
              aria-label={`Pick ${p.display_name}`}
              className={[
                "group relative flex flex-col overflow-hidden rounded-lg border text-left transition-all",
                isSelected
                  ? "border-aether-accent bg-aether-elevated shadow-lg"
                  : "border-aether-border bg-aether-bg hover:border-aether-text/40 hover:bg-aether-elevated",
              ].join(" ")}
            >
              <div className="aspect-square w-full overflow-hidden bg-aether-elevated">
                <img
                  src={previewAssetUrl(p.preview_webp)}
                  alt={`${p.display_name} portrait`}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              </div>
              <div className="flex flex-col gap-1.5 p-4">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-[14px] font-medium text-aether-text">
                    {p.display_name}
                  </h2>
                  <span
                    className="font-mono text-[10px] uppercase tracking-wider text-aether-dim"
                    aria-label={`archetype ${p.archetype}`}
                  >
                    {p.archetype.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-[12px] leading-relaxed text-aether-muted">
                  {p.tagline}
                </p>
                {isPlaying && (
                  <span
                    className="text-[10px] font-mono uppercase tracking-wider text-aether-accent"
                    aria-live="polite"
                  >
                    Playing voice…
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-8 flex justify-end">
        <button
          type="button"
          disabled={!selected}
          className={[
            "rounded-md px-4 py-2 text-[12px] font-medium transition-colors",
            selected
              ? "border border-aether-accent bg-aether-accent/10 text-aether-accent hover:bg-aether-accent/20"
              : "border border-aether-border text-aether-dim",
          ].join(" ")}
          onClick={() => selected && setStep("confirm")}
        >
          {selected ? `Continue with ${selected.display_name}` : "Pick a companion to continue"}
        </button>
      </div>
    </div>
  );
}
